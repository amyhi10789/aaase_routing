from flask import Flask, request, jsonify, send_from_directory, session, render_template_string
from flask_cors import CORS
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv
import uuid
from datetime import datetime
import json
import traceback
import time
import re
import math
import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt

load_dotenv()

app = Flask(__name__, static_folder="frontend", static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")
CORS(app, supports_credentials=True)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")
MAPS_API_KEY = os.getenv("MAPS_JAVASCRIPT_KEY")
PLACES_API_KEY = os.getenv("PLACES_KEY")
DIRECTIONS_API_KEY = os.getenv("DIRECTIONS_KEY")
ROUTES_API_KEY = os.getenv("ROUTES_KEY")

# Store conversation history and plotted points (in production, use Redis or database)
conversation_history = {}
user_plotted_points = {}

# Cache for API responses to improve performance
api_cache = {}
CACHE_DURATION = 300  # 5 minutes

def get_or_create_session_id():
    """Get existing session ID or create a new one"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_conversation_history(session_id):
    """Get conversation history for a session"""
    if session_id not in conversation_history:
        conversation_history[session_id] = []
    return conversation_history[session_id]

def get_user_plotted_points(session_id):
    """Get plotted points for a session"""
    if session_id not in user_plotted_points:
        user_plotted_points[session_id] = []
    return user_plotted_points[session_id]

def add_plotted_point(session_id, point_data):
    """Add a plotted point to user's session"""
    if session_id not in user_plotted_points:
        user_plotted_points[session_id] = []
    
    point = {
        "id": point_data.get("id", len(user_plotted_points[session_id]) + 1),
        "lat": float(point_data["lat"]),
        "lng": float(point_data["lng"]),
        "name": point_data.get("name", f"Point {len(user_plotted_points[session_id]) + 1}"),
        "timestamp": datetime.now().isoformat(),
        "address": point_data.get("address", ""),
        "notes": point_data.get("notes", "")
    }
    
    user_plotted_points[session_id].append(point)
    return point

def remove_plotted_point(session_id, point_id):
    """Remove a plotted point from user's session"""
    if session_id not in user_plotted_points:
        return False
    
    user_plotted_points[session_id] = [
        p for p in user_plotted_points[session_id] if p["id"] != point_id
    ]
    return True

def calculate_distance_between_points(lat1, lng1, lat2, lng2):
    """Calculate distance between two points using Haversine formula"""
    # Convert latitude and longitude from degrees to radians
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    
    return c * r

def calculate_total_route_distance(points):
    """Calculate total distance for a route through multiple points"""
    if len(points) < 2:
        return 0
    
    total_distance = 0
    for i in range(len(points) - 1):
        distance = calculate_distance_between_points(
            points[i]["lat"], points[i]["lng"],
            points[i + 1]["lat"], points[i + 1]["lng"]
        )
        total_distance += distance
    
    return total_distance

def add_to_conversation_history(session_id, user_message, bot_response, location):
    """Add a message pair to conversation history"""
    if session_id not in conversation_history:
        conversation_history[session_id] = []
    
    conversation_history[session_id].append({
        "timestamp": datetime.now().isoformat(),
        "location": location,
        "user_message": user_message,
        "bot_response": bot_response
    })
    
    # Keep only last 10 conversations to prevent context from getting too long
    if len(conversation_history[session_id]) > 10:
        conversation_history[session_id] = conversation_history[session_id][-10:]

def is_cache_valid(cache_key):
    """Check if cached data is still valid"""
    if cache_key not in api_cache:
        return False
    
    cache_time = api_cache[cache_key].get('timestamp', 0)
    return (time.time() - cache_time) < CACHE_DURATION

def get_from_cache(cache_key):
    """Get data from cache if valid"""
    if is_cache_valid(cache_key):
        return api_cache[cache_key]['data']
    return None

def set_cache(cache_key, data):
    """Store data in cache with timestamp"""
    api_cache[cache_key] = {
        'data': data,
        'timestamp': time.time()
    }

def geocode_place(place_name):
    """Geocode a place name to coordinates using Google Geocoding API"""
    if not PLACES_API_KEY:
        return None
    
    cache_key = f"geocode_place_{place_name}"
    cached_result = get_from_cache(cache_key)
    if cached_result:
        return cached_result
    
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'address': place_name,
            'key': PLACES_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK' and data['results']:
                result = data['results'][0]
                location_data = {
                    'lat': result['geometry']['location']['lat'],
                    'lng': result['geometry']['location']['lng'],
                    'formatted_address': result['formatted_address'],
                    'place_id': result.get('place_id', ''),
                    'types': result.get('types', [])
                }
                set_cache(cache_key, location_data)
                return location_data
        return None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None

def get_place_suggestions(query, location=None):
    """Get place suggestions using Google Places Autocomplete API"""
    if not PLACES_API_KEY:
        return []
    
    cache_key = f"suggestions_{query}_{location}"
    cached_result = get_from_cache(cache_key)
    if cached_result:
        return cached_result
    
    try:
        url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
        params = {
            'input': query,
            'key': PLACES_API_KEY,
            'types': 'establishment',
            'components': 'country:us'
        }
        
        if location:
            params['location'] = f"{location['lat']},{location['lng']}"
            params['radius'] = 50000
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                suggestions = []
                for prediction in data.get('predictions', []):
                    suggestions.append({
                        'place_id': prediction['place_id'],
                        'description': prediction['description'],
                        'main_text': prediction['structured_formatting']['main_text'],
                        'secondary_text': prediction['structured_formatting'].get('secondary_text', ''),
                        'types': prediction.get('types', [])
                    })
                set_cache(cache_key, suggestions)
                return suggestions
        return []
    except Exception as e:
        print(f"Places suggestions error: {e}")
        return []

def detect_location_intent(message):
    """Detect if the user wants to navigate to a specific location using NLP patterns"""
    message_lower = message.lower().strip()
    
    # Patterns that indicate location navigation intent
    navigation_patterns = [
        r'(?:show me|take me to|go to|navigate to|find|locate|search for)\s+(.+)',
        r'(?:where is|what\'s at|crime at|safety at|how safe is)\s+(.+)',
        r'(?:i want to go to|i\'m going to|heading to|going to visit)\s+(.+)',
        r'(?:directions to|route to|how to get to)\s+(.+)',
        r'(?:is\s+)?(.+?)\s+(?:safe|dangerous|crime|crimes)',
        r'crime (?:in|at|near)\s+(.+)',
        r'safety (?:in|at|near)\s+(.+)',
        r'(.+?)\s+crime rate',
        r'(.+?)\s+crime statistics',
    ]
    
    for pattern in navigation_patterns:
        match = re.search(pattern, message_lower)
        if match:
            potential_location = match.group(1).strip()
            # Clean up the extracted location
            potential_location = clean_location_string(potential_location)
            if is_valid_location(potential_location):
                return potential_location
    
    # Check for standalone location mentions (e.g., just "New York" or "Central Park")
    if is_standalone_location(message_lower):
        return clean_location_string(message_lower)
    
    return None

def clean_location_string(location):
    """Clean and normalize location string"""
    # Remove common stop words that aren't part of location names
    stop_words = ['the', 'a', 'an', 'is', 'are', 'was', 'were', 'very', 'really', 'quite', 'so', 'too']
    words = location.split()
    cleaned_words = [word for word in words if word.lower() not in stop_words]
    return ' '.join(cleaned_words).strip()

def is_valid_location(location):
    """Check if the extracted text looks like a valid location"""
    if not location or len(location) < 2:
        return False
    
    # Filter out common non-location words
    invalid_terms = [
        'here', 'there', 'this', 'that', 'it', 'they', 'them', 'us', 'we',
        'crime', 'safety', 'safe', 'dangerous', 'area', 'place', 'location',
        'statistics', 'rate', 'news', 'report', 'incident'
    ]
    
    if location.lower() in invalid_terms:
        return False
    
    # Must contain at least one letter
    if not re.search(r'[a-zA-Z]', location):
        return False
    
    return True

def is_standalone_location(message):
    """Check if the message is likely just a location name"""
    words = message.split()
    if len(words) > 4:  # Too many words to be a simple location
        return False
    
    # Common location indicators
    location_indicators = [
        'park', 'street', 'ave', 'avenue', 'road', 'rd', 'blvd', 'boulevard',
        'square', 'plaza', 'center', 'centre', 'mall', 'university', 'college',
        'hospital', 'airport', 'station', 'beach', 'mountain', 'lake', 'river',
        'city', 'town', 'village', 'county'
    ]
    
    return any(indicator in message for indicator in location_indicators)

def reverse_geocode(lat, lng):
    """Reverse geocode coordinates to location name with caching"""
    cache_key = f"geocode_{lat}_{lng}"
    cached_result = get_from_cache(cache_key)
    if cached_result:
        return cached_result
    
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=10"
        response = requests.get(url, headers={'User-Agent': 'SafePath/1.0'}, timeout=10)
        
        if response.status_code != 200:
            return "unknown location"
            
        data = response.json()
        address = data.get("address", {})
        
        # Try to get the most specific location available
        city = address.get("city") or address.get("town") or address.get("village")
        county = address.get("county")
        state = address.get("state")
        country = address.get("country")
        
        # Build location string
        location_parts = []
        if city:
            location_parts.append(city)
        if county and county != city:
            location_parts.append(county)
        if state:
            location_parts.append(state)
        if country:
            location_parts.append(country)
            
        result = ", ".join(location_parts) if location_parts else "unknown location"
        set_cache(cache_key, result)
        return result
        
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return "unknown location"

def get_place_details(place_id):
    """Get detailed information about a place using Google Places API"""
    if not PLACES_API_KEY:
        return None
    
    cache_key = f"place_{place_id}"
    cached_result = get_from_cache(cache_key)
    if cached_result:
        return cached_result
    
    try:
        url = f"https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_address,geometry,rating,types,photos,reviews',
            'key': PLACES_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                result = data['result']
                set_cache(cache_key, result)
                return result
        return None
    except Exception as e:
        print(f"Places API error: {e}")
        return None

def search_nearby_places(lat, lng, place_type="point_of_interest", radius=5000):
    """Search for nearby places using Google Places API"""
    if not PLACES_API_KEY:
        return []
    
    cache_key = f"nearby_{lat}_{lng}_{place_type}_{radius}"
    cached_result = get_from_cache(cache_key)
    if cached_result:
        return cached_result
    
    try:
        url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            'location': f"{lat},{lng}",
            'radius': radius,
            'type': place_type,
            'key': PLACES_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                result = data['results'][:10]  # Return top 10 results
                set_cache(cache_key, result)
                return result
        return []
    except Exception as e:
        print(f"Places search error: {e}")
        return []

def get_directions(origin, destination, mode='driving'):
    """Get directions using Google Directions API"""
    if not DIRECTIONS_API_KEY:
        return None
    
    try:
        url = f"https://maps.googleapis.com/maps/api/directions/json"
        params = {
            'origin': f"{origin['lat']},{origin['lng']}",
            'destination': f"{destination['lat']},{destination['lng']}",
            'mode': mode,
            'alternatives': 'true',
            'key': DIRECTIONS_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                return data
        return None
    except Exception as e:
        print(f"Directions API error: {e}")
        return None

def get_routes(origin, destination, travel_mode='DRIVE'):
    """Get routes using Google Routes API (newer API)"""
    if not ROUTES_API_KEY:
        return None
    
    try:
        url = f"https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': ROUTES_API_KEY,
            'X-Goog-FieldMask': 'routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline'
        }
        
        data = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": origin['lat'],
                        "longitude": origin['lng']
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": destination['lat'],
                        "longitude": destination['lng']
                    }
                }
            },
            "travelMode": travel_mode,
            "routingPreference": "TRAFFIC_AWARE",
            "computeAlternativeRoutes": True
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Routes API error: {e}")
        return None

def fetch_crime_news(location=None, global_query=None):
    """Fetch recent crime and safety news with improved error handling and caching"""
    cache_key = f"news_{location or 'global'}_{global_query or 'default'}"
    cached_result = get_from_cache(cache_key)
    if cached_result:
        return cached_result
    
    if not GNEWS_API_KEY:
        print("GNews API key not configured")
        return []
        
    try:
        if global_query:
            # For global or specific location queries from user
            search_queries = [
                global_query,
                f"{global_query} crime",
                f"{global_query} safety",
                f"{global_query} police"
            ]
        elif location:
            # For user's current location
            search_queries = [
                f"crime safety {location}",
                f"police incident {location}",
                f"violence robbery theft {location}",
                f"{location} crime news"
            ]
        else:
            # Global crime news
            search_queries = [
                "global crime news",
                "international crime statistics", 
                "world crime trends",
                "crime news worldwide"
            ]
        
        all_articles = []
        
        for query in search_queries[:2]:  # Limit to first 2 queries to speed up
            try:
                url = "https://gnews.io/api/v4/search"
                params = {
                    "q": query,
                    "lang": "en",
                    "max": 3,  # Reduced per query to get variety
                    "sortby": "publishedAt",  # Get most recent first
                    "apikey": GNEWS_API_KEY
                }
                
                # Don't restrict to US for global queries
                if location and not global_query:
                    params["country"] = "us"
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    articles = data.get("articles", [])
                    
                    for article in articles:
                        # Avoid duplicates by checking titles
                        if not any(existing["title"] == article["title"] for existing in all_articles):
                            all_articles.append({
                                "title": article["title"],
                                "description": article["description"],
                                "url": article["url"],
                                "publishedAt": article["publishedAt"],
                                "source": article.get("source", {}).get("name", "Unknown"),
                                "query_used": query,
                                "query_type": "global" if global_query or not location else "local"
                            })
                elif response.status_code == 429:
                    print("GNews API rate limit exceeded")
                    break
                else:
                    print(f"GNews API error for query '{query}': {response.status_code}")
                    
            except requests.RequestException as e:
                print(f"Network error fetching news for query '{query}': {str(e)}")
                continue
        
        # Sort by publication date (most recent first) and limit to 8 total
        all_articles.sort(key=lambda x: x["publishedAt"], reverse=True)
        result = all_articles[:8]
        set_cache(cache_key, result)
        return result
        
    except Exception as e:
        print(f"News API error: {str(e)}")
        return []

def extract_location_from_query(message):
    """Extract location mentions from user queries for global crime questions"""
    message_lower = message.lower()
    
    # Known cities/countries/regions to look for
    locations = [
        'new york', 'los angeles', 'chicago', 'houston', 'philadelphia',
        'london', 'paris', 'tokyo', 'beijing', 'moscow', 'mumbai',
        'canada', 'mexico', 'brazil', 'argentina', 'uk', 'france', 'germany',
        'italy', 'spain', 'japan', 'china', 'india', 'australia', 'russia',
        'california', 'texas', 'florida', 'new york state', 'washington',
        'miami', 'boston', 'seattle', 'denver', 'atlanta', 'detroit', 'korea',
        ''
    ]
    
    for location in locations:
        if location in message_lower:
            return location
    
    import re
    # Common location patterns
    location_patterns = [
        r'in ([A-Za-z\s]+?)(?:\s|$|[,.])',
        r'from ([A-Za-z\s]+?)(?:\s|$|[,.])',
        r'about ([A-Za-z\s]+?)(?:\s|$|[,.])',
        r'([A-Za-z\s]+?) crime',
        r'([A-Za-z\s]+?) safety',
        r'([A-Za-z\s]+?) statistics'
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, message_lower)
        if match:
            potential_location = match.group(1).strip()
            if len(potential_location) > 2 and potential_location not in ['the', 'and', 'for', 'with']:
                return potential_location
    
    return None

def is_global_crime_query(message):
    """Check if the user is asking about crime in other locations or globally"""
    message_lower = message.lower()
    
    global_indicators = [
        'worldwide', 'globally', 'international', 'around the world',
        'other countries', 'globally', 'world crime', 'international crime'
    ]
    
    # Check for explicit global terms
    if any(indicator in message_lower for indicator in global_indicators):
        return True, None
    
    # Check for specific location mentions
    extracted_location = extract_location_from_query(message)
    if extracted_location:
        return True, extracted_location
        
    return False, None

def format_news_for_ai(articles):
    """Format news articles in a structured way for the AI"""
    if not articles:
        return "No recent crime or safety news found for this location."
    
    formatted_news = f"AVAILABLE NEWS DATA ({len(articles)} articles):\n\n"
    
    for i, article in enumerate(articles, 1):
        # Parse date to make it more readable
        try:
            from datetime import datetime
            pub_date = datetime.fromisoformat(article["publishedAt"].replace('Z', '+00:00'))
            readable_date = pub_date.strftime("%B %d, %Y")
            days_ago = (datetime.now(pub_date.tzinfo) - pub_date).days
            recency = f"({days_ago} days ago)" if days_ago > 0 else "(Today)"
        except:
            readable_date = article["publishedAt"]
            recency = ""
        
        formatted_news += f"ARTICLE #{i}:\n"
        formatted_news += f"HEADLINE: \"{article['title']}\"\n"
        formatted_news += f"SOURCE: {article['source']}\n"
        formatted_news += f"PUBLISHED: {readable_date} {recency}\n"
        formatted_news += f"DESCRIPTION: {article['description']}\n"
        formatted_news += "=" * 60 + "\n\n"
    
    return formatted_news

def is_crime_or_safety_related(message):
    """Check if the user's message is related to crime or safety"""
    message_lower = message.lower()
    
    crime_safety_keywords = [
        'crime', 'crimes', 'criminal', 'safety', 'safe', 'dangerous', 'danger',
        'security', 'violence', 'violent', 'assault', 'robbery', 'theft', 'steal',
        'murder', 'homicide', 'shooting', 'stabbing', 'burglary', 'break-in',
        'vandalism', 'drug', 'drugs', 'gang', 'gangs', 'police', 'arrest',
        'attack', 'mugging', 'fraud', 'scam', 'harassment', 'domestic violence',
        'kidnapping', 'rape', 'sexual assault', 'stalking', 'threats',
        'crime rate', 'crime statistics', 'police report', 'incident',
        'law enforcement', 'criminal activity', 'public safety', 'neighborhood',
        'area', 'location', 'here', 'near', 'around', 'show me', 'take me to',
        'go to', 'navigate to', 'find', 'locate', 'where is', 'directions',
        'plot', 'point', 'marker', 'route', 'distance', 'path'
    ]
    
    return any(keyword in message_lower for keyword in crime_safety_keywords)

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        message = data.get("message")
        lat = data.get("lat")
        lng = data.get("lng")

        if not message:
            return jsonify({"error": "Message is required"}), 400
            
        if lat is None or lng is None:
            return jsonify({"error": "Location coordinates are required"}), 400

        # Get session ID
        session_id = get_or_create_session_id()
        
        # Get location name
        location = reverse_geocode(lat, lng)
        
        # Check for location navigation intent first
        detected_location = detect_location_intent(message)
        location_data = None
        
        if detected_location:
            print(f"Detected location intent: {detected_location}")
            location_data = geocode_place(detected_location)
            
            if location_data:
                print(f"Successfully geocoded: {location_data}")
                # Get crime data for the requested location
                requested_location = location_data['formatted_address']
                crime_articles = fetch_crime_news(global_query=detected_location)
                formatted_articles = format_news_for_ai(crime_articles)
                
                # Create response with location information
                response_text = f"I found {detected_location} on the map! I've moved the map to show you this location: {location_data['formatted_address']}. "
                
                # Add crime/safety info if available
                if crime_articles:
                    response_text += f"Here's what I found about safety in that area: {formatted_articles[:200]}..."
                else:
                    response_text += "I don't have recent crime data for this specific location, but I've marked it on the map for you."
                
                add_to_conversation_history(session_id, message, response_text, location)
                
                return jsonify({
                    "response": response_text,
                    "location_found": True,
                    "location_data": location_data
                })
            else:
                response_text = f"I couldn't find the exact location '{detected_location}' on the map. Could you try being more specific or check the spelling?"
                add_to_conversation_history(session_id, message, response_text, location)
                
                return jsonify({
                    "response": response_text,
                    "location_found": False
                })
        
        # Check if query is crime/safety related
        if not is_crime_or_safety_related(message):
            response_text = "I'm sorry, I can only answer questions related to crime and safety in your area. Please ask about local crime statistics, safety concerns, or security issues."
            add_to_conversation_history(session_id, message, response_text, location)
            return jsonify({"response": response_text})
        
        # Check for global queries
        is_global, global_location = is_global_crime_query(message)
        
        # Get crime and safety related news
        if is_global and global_location:
            crime_articles = fetch_crime_news(global_query=global_location)
        else:
            crime_articles = fetch_crime_news(location)
            
        formatted_articles = format_news_for_ai(crime_articles)

        # Get conversation history and plotted points
        history = get_conversation_history(session_id)
        plotted_points = get_user_plotted_points(session_id)
        
        # Include plotted points context
        plotted_points_context = ""
        if plotted_points:
            plotted_points_context = f"\n\nUser's plotted points ({len(plotted_points)} points):\n"
            total_distance = calculate_total_route_distance(plotted_points)
            plotted_points_context += f"Total route distance: {total_distance:.2f} km\n"
            
            for i, point in enumerate(plotted_points, 1):
                plotted_points_context += f"{i}. {point['name']} at ({point['lat']:.4f}, {point['lng']:.4f}) - {point['timestamp'][:16]}\n"

        conversation_context = ""
        if history:
            conversation_context = "Previous conversation context:\n"
            for conv in history[-3:]:  # Last 3 exchanges
                conversation_context += f"User: {conv['user_message']}\nBot: {conv['bot_response']}\n\n"

        system_prompt = f"""
You are a specialized safety and crime information chatbot for location-aware services. You do not specialize in any specific location around the world. You can provide information from around the world, information from every country to users.
The user is currently located in: {location} (coordinates: {lat}, {lng})

Your role is to provide information ONLY about:
- Crime statistics and trends in any location as long as the user asks for it
- Safety concerns and recommendations
- Specific recent criminal incidents or police reports
- Security tips depending on the location asked for by the user
- Violence, theft, assault, burglary, and other criminal activities
- Police presence and law enforcement updates
- Safety ratings and concerns
- Help with plotting points and route planning for safety purposes

Recent crime and safety news for {location}:
{formatted_articles}

{plotted_points_context}

Always reference the specific location ({location}) in your responses when relevant.
Provide helpful, accurate, and location-specific crime and safety information.
If you don't have specific crime data about their exact location, acknowledge this and provide general safety guidance for similar areas.
Keep responses focused strictly on crime and safety topics.
Keep your responses short - always make sure they're under 100 words.
Don't use too many buzzwords - make it sound human.
Be polite to the user.

If the user asks about their plotted points, routes, or distances, use the plotted points context provided above.
"""

        # Prepare messages for OpenAI
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add recent conversation history
        for conv in history[-2:]:  # Last 2 exchanges for context
            messages.append({"role": "user", "content": conv['user_message']})
            messages.append({"role": "assistant", "content": conv['bot_response']})
            
        # Add current message
        messages.append({"role": "user", "content": message})

        # Get AI response
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0.7,
            timeout=15
        )

        reply = response.choices[0].message.content.strip()
        
        # Store in conversation history
        add_to_conversation_history(session_id, message, reply, location)
        
        return jsonify({"response": reply})

    except requests.exceptions.RequestException as e:
        print(f"Network error in chat: {str(e)}")
        return jsonify({"response": "I'm having trouble connecting to my data sources right now. Please try again in a moment."}), 500
        
    except Exception as e:
        print(f"Error processing chat request: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"response": "Sorry, I encountered an error. Please try rephrasing your question or try again later."}), 500

# Global variable to store crime data (in production, use a database)
crime_data = None
violent_crime_types = {
    # Common violent crime categories - adjust based on your dataset
    'homicide', 'murder', 'manslaughter', 'assault', 'aggravated assault', 
    'simple assault', 'robbery', 'armed robbery', 'rape', 'sexual assault',
    'kidnapping', 'domestic violence', 'battery', 'shooting', 'stabbing',
    'carjacking', 'purse snatching', 'strong arm robbery', 'other assault', 'theft'
}

def load_crime_data():
    """Load and process the Philadelphia crime dataset"""
    global crime_data
    try:
        # Load the CSV file
        df = pd.read_csv('safepath-maps/philly_crime_data.csv')
        
        # Extract lat/lng from columns 17 and 18 (0-indexed: 16 and 17)
        if len(df.columns) >= 18:
            # Assuming 0-based indexing
            lat_col = df.columns[16]  # 17th column
            lng_col = df.columns[17]  # 18th column
            
            # Clean and convert coordinates
            df['latitude'] = pd.to_numeric(df[lat_col], errors='coerce')
            df['longitude'] = pd.to_numeric(df[lng_col], errors='coerce')
            
            # Remove rows with invalid coordinates
            df = df.dropna(subset=['latitude', 'longitude'])
            
            # Filter for Philadelphia area (rough bounds)
            df = df[
                (df['latitude'] >= 39.0) & (df['latitude'] <= 41.0) &
                (df['longitude'] >= -76.0) & (df['longitude'] <= -74.0)
            ]
            
            # Add violent crime classification
            df['is_violent_crime'] = df.apply(classify_violent_crime, axis=1)
            
            crime_data = df
            print(f"Loaded {len(crime_data)} crime records")
            print(f"Violent crimes: {len(crime_data[crime_data['is_violent_crime']])}")
            
            return True
        else:
            print("CSV doesn't have enough columns")
            return False
            
    except FileNotFoundError:
        print("philly_crime_data.csv not found")
        return False
    except Exception as e:
        print(f"Error loading crime data: {e}")
        return False

def classify_violent_crime(row):
    """Classify if a crime is violent based on description/category"""
    # Check common crime description columns
    description_cols = ['description', 'crime_type', 'offense', 'incident_type', 'ucr_general']
    
    for col in description_cols:
        if col in row.index and pd.notna(row[col]):
            description = str(row[col]).lower()
            if any(violent_type in description for violent_type in violent_crime_types):
                return True
    
    return False

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    Returns distance in feet
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # Radius of earth in feet (approximately)
    r = 20902231  # feet
    
    return c * r

def get_crimes_within_radius(lat, lng, radius_feet=500):
    """Get violent crimes within specified radius of a point"""
    if crime_data is None or crime_data.empty:
        return {
            'total_crimes': 0,
            'violent_crimes': 0,
            'crime_details': [],
            'error': 'Crime data not loaded'
        }
    
    try:
        # Calculate distances for all crime points
        distances = crime_data.apply(
            lambda row: haversine_distance(lat, lng, row['latitude'], row['longitude']), 
            axis=1
        )
        
        # Filter crimes within radius
        nearby_crimes = crime_data[distances <= radius_feet].copy()
        nearby_crimes['distance_feet'] = distances[distances <= radius_feet]
        
        # Filter for violent crimes
        violent_crimes = nearby_crimes[nearby_crimes['is_violent_crime']]
        
        # Prepare detailed crime information
        crime_details = []
        for _, crime in violent_crimes.head(10).iterrows():  # Limit to 10 most recent
            detail = {
                'distance_feet': round(crime['distance_feet'], 1),
                'latitude': crime['latitude'],
                'longitude': crime['longitude']
            }
            
            # Add available crime information
            info_cols = ['description', 'crime_type', 'offense', 'incident_type', 'ucr_general', 'date', 'time']
            for col in info_cols:
                if col in crime.index and pd.notna(crime[col]):
                    detail[col] = str(crime[col])
            
            crime_details.append(detail)
        
        return {
            'total_crimes': len(nearby_crimes),
            'violent_crimes': len(violent_crimes),
            'crime_details': crime_details,
            'radius_feet': radius_feet,
            'search_location': {'lat': lat, 'lng': lng}
        }
        
    except Exception as e:
        print(f"Error getting crimes within radius: {e}")
        return {
            'total_crimes': 0,
            'violent_crimes': 0,
            'crime_details': [],
            'error': str(e)
        }

def get_crime_density_map(bounds, grid_size=20):
    """Get crime density data for map visualization"""
    if crime_data is None:
        return {'error': 'Crime data not loaded'}
    
    try:
        # Extract bounds
        north = bounds['north']
        south = bounds['south']
        east = bounds['east']
        west = bounds['west']
        
        # Filter crimes within bounds
        bounded_crimes = crime_data[
            (crime_data['latitude'] >= south) & (crime_data['latitude'] <= north) &
            (crime_data['longitude'] >= west) & (crime_data['longitude'] <= east) &
            (crime_data['is_violent_crime'] == True)
        ]
        
        if bounded_crimes.empty:
            return {'density_points': []}
        
        # Create grid
        lat_step = (north - south) / grid_size
        lng_step = (east - west) / grid_size
        
        density_points = []
        
        for i in range(grid_size):
            for j in range(grid_size):
                grid_lat = south + (i + 0.5) * lat_step
                grid_lng = west + (j + 0.5) * lng_step
                
                # Count crimes within this grid cell
                cell_crimes = bounded_crimes[
                    (bounded_crimes['latitude'] >= south + i * lat_step) &
                    (bounded_crimes['latitude'] < south + (i + 1) * lat_step) &
                    (bounded_crimes['longitude'] >= west + j * lng_step) &
                    (bounded_crimes['longitude'] < west + (j + 1) * lng_step)
                ]
                
                if len(cell_crimes) > 0:
                    density_points.append({
                        'lat': grid_lat,
                        'lng': grid_lng,
                        'count': len(cell_crimes),
                        'intensity': min(len(cell_crimes) / 10.0, 1.0)  # Normalize to 0-1
                    })
        
        return {'density_points': density_points}
        
    except Exception as e:
        return {'error': str(e)}

# API endpoint for crime data within radius
@app.route("/api/crimes-nearby", methods=["POST"])
def crimes_nearby():
    """Get violent crimes within radius of a point"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        lat = data.get("lat")
        lng = data.get("lng")
        radius = data.get("radius", 500)  # Default 500 feet
        
        if lat is None or lng is None:
            return jsonify({"error": "Latitude and longitude are required"}), 400
        
        # Load crime data if not already loaded
        if crime_data is None:
            if not load_crime_data():
                return jsonify({"error": "Failed to load crime data"}), 500
        
        # Get crimes within radius
        result = get_crimes_within_radius(lat, lng, radius)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in crimes_nearby: {e}")
        return jsonify({"error": "Failed to get nearby crimes"}), 500

# API endpoint for crime density heatmap
@app.route("/api/crime-density", methods=["POST"])
def crime_density():
    """Get crime density data for heatmap visualization"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        bounds = data.get("bounds")
        grid_size = data.get("grid_size", 20)
        
        if not bounds:
            return jsonify({"error": "Map bounds are required"}), 400
        
        # Load crime data if not already loaded
        if crime_data is None:
            if not load_crime_data():
                return jsonify({"error": "Failed to load crime data"}), 500
        
        # Get density data
        result = get_crime_density_map(bounds, grid_size)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in crime_density: {e}")
        return jsonify({"error": "Failed to get crime density"}), 500

# API endpoint to reload crime data
@app.route("/api/reload-crime-data", methods=["POST"])
def reload_crime_data():
    """Reload the crime dataset"""
    try:
        success = load_crime_data()
        if success:
            return jsonify({
                "success": True, 
                "message": "Crime data reloaded successfully",
                "total_records": len(crime_data),
                "violent_crimes": len(crime_data[crime_data['is_violent_crime']])
            })
        else:
            return jsonify({"error": "Failed to reload crime data"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Initialize crime data when the app starts
try:
    load_crime_data()
except Exception as e:
    print(f"Failed to load crime data on startup: {e}")

@app.route("/api/plot-point", methods=["POST"])
def plot_point():
    """Add a point to user's plotted points"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        lat = data.get("lat")
        lng = data.get("lng")
        name = data.get("name", "")
        address = data.get("address", "")
        notes = data.get("notes", "")
        
        if lat is None or lng is None:
            return jsonify({"error": "Latitude and longitude are required"}), 400
        
        session_id = get_or_create_session_id()
        
        point_data = {
            "lat": lat,
            "lng": lng,
            "name": name or f"Point {len(get_user_plotted_points(session_id)) + 1}",
            "address": address,
            "notes": notes
        }
        
        point = add_plotted_point(session_id, point_data)
        
        # Calculate new total distance
        points = get_user_plotted_points(session_id)
        total_distance = calculate_total_route_distance(points)
        
        return jsonify({
            "success": True,
            "point": point,
            "total_points": len(points),
            "total_distance_km": round(total_distance, 2)
        })
        
    except Exception as e:
        print(f"Error plotting point: {str(e)}")
        return jsonify({"error": "Failed to plot point"}), 500

@app.route("/api/remove-point", methods=["POST"])
def remove_point():
    """Remove a point from user's plotted points"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        point_id = data.get("point_id")
        if point_id is None:
            return jsonify({"error": "Point ID is required"}), 400
        
        session_id = get_or_create_session_id()
        
        success = remove_plotted_point(session_id, point_id)
        
        if success:
            # Calculate new total distance
            points = get_user_plotted_points(session_id)
            total_distance = calculate_total_route_distance(points)
            
            return jsonify({
                "success": True,
                "total_points": len(points),
                "total_distance_km": round(total_distance, 2)
            })
        else:
            return jsonify({"error": "Point not found"}), 404
            
    except Exception as e:
        print(f"Error removing point: {str(e)}")
        return jsonify({"error": "Failed to remove point"}), 500

@app.route("/api/get-plotted-points", methods=["GET"])
def get_plotted_points():
    """Get all plotted points for the current session"""
    try:
        session_id = get_or_create_session_id()
        points = get_user_plotted_points(session_id)
        total_distance = calculate_total_route_distance(points)
        
        return jsonify({
            "points": points,
            "total_points": len(points),
            "total_distance_km": round(total_distance, 2)
        })
        
    except Exception as e:
        print(f"Error getting plotted points: {str(e)}")
        return jsonify({"error": "Failed to get plotted points"}), 500

@app.route("/api/clear-plotted-points", methods=["POST"])
def clear_plotted_points():
    """Clear all plotted points for the current session"""
    try:
        session_id = get_or_create_session_id()
        
        if session_id in user_plotted_points:
            user_plotted_points[session_id] = []
        
        return jsonify({
            "success": True,
            "total_points": 0,
            "total_distance_km": 0
        })
        
    except Exception as e:
        print(f"Error clearing plotted points: {str(e)}")
        return jsonify({"error": "Failed to clear plotted points"}), 500

@app.route("/api/places/suggestions", methods=["POST"])
def places_suggestions():
    """Get place suggestions for autocomplete"""
    try:
        data = request.get_json()
        query = data.get("query", "")
        lat = data.get("lat")
        lng = data.get("lng")
        
        if not query or len(query) < 2:
            return jsonify({"suggestions": []})
        
        location = None
        if lat is not None and lng is not None:
            location = {"lat": lat, "lng": lng}
        
        suggestions = get_place_suggestions(query, location)
        return jsonify({"suggestions": suggestions})
        
    except Exception as e:
        print(f"Places suggestions error: {str(e)}")
        return jsonify({"error": "Failed to get suggestions"}), 500

@app.route("/api/places/search", methods=["POST"])
def search_places():
    """Search for places using Google Places API"""
    try:
        data = request.get_json()
        query = data.get("query")
        lat = data.get("lat", 0)
        lng = data.get("lng", 0)
        
        if not query:
            return jsonify({"error": "Query is required"}), 400
        
        places = search_nearby_places(lat, lng, query)
        return jsonify({"places": places})
        
    except Exception as e:
        print(f"Places search error: {str(e)}")
        return jsonify({"error": "Failed to search places"}), 500

@app.route("/api/places/details", methods=["POST"])
def place_details():
    """Get place details using Google Places API"""
    try:
        data = request.get_json()
        place_id = data.get("place_id")
        
        if not place_id:
            return jsonify({"error": "Place ID is required"}), 400
        
        details = get_place_details(place_id)
        if details:
            return jsonify({"place": details})
        else:
            return jsonify({"error": "Place not found"}), 404
            
    except Exception as e:
        print(f"Place details error: {str(e)}")
        return jsonify({"error": "Failed to get place details"}), 500

@app.route("/api/directions", methods=["POST"])
def directions():
    """Get directions using Google Directions API"""
    try:
        data = request.get_json()
        origin = data.get("origin")
        destination = data.get("destination")
        mode = data.get("mode", "driving")
        
        if not origin or not destination:
            return jsonify({"error": "Origin and destination are required"}), 400
        
        directions_result = get_directions(origin, destination, mode)
        if directions_result:
            return jsonify(directions_result)
        else:
            return jsonify({"error": "Directions not found"}), 404
            
    except Exception as e:
        print(f"Directions error: {str(e)}")
        return jsonify({"error": "Failed to get directions"}), 500

@app.route("/api/calculate-route-distance", methods=["POST"])
def calculate_route_distance():
    """Calculate total distance for a route through multiple points"""
    try:
        data = request.get_json()
        points = data.get("points", [])
        
        if len(points) < 2:
            return jsonify({"distance_km": 0, "message": "Need at least 2 points"})
        
        total_distance = calculate_total_route_distance(points)
        
        return jsonify({
            "distance_km": round(total_distance, 2),
            "total_points": len(points)
        })
        
    except Exception as e:
        print(f"Distance calculation error: {str(e)}")
        return jsonify({"error": "Failed to calculate distance"}), 500

@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        # Check if critical services are configured
        services = {
            "openai": bool(client.api_key),
            "gnews": bool(GNEWS_API_KEY),
            "maps": bool(MAPS_API_KEY),
            "places": bool(PLACES_API_KEY),
        }
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": services,
            "cache_size": len(api_cache),
            "active_sessions": len(conversation_history),
            "total_plotted_points": sum(len(points) for points in user_plotted_points.values())
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route("/api/clear-cache", methods=["POST"])
def clear_cache():
    """Clear API cache"""
    try:
        api_cache.clear()
        return jsonify({"message": "Cache cleared successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/clear-history", methods=["POST"])
def clear_history():
    """Clear conversation history"""
    try:
        session_id = session.get('session_id')
        if session_id and session_id in conversation_history:
            del conversation_history[session_id]
        return jsonify({"message": "Conversation history cleared"})
    except Exception as e:
        return jsonify({"error": "Failed to clear history"}), 500

@app.route("/api/session-stats", methods=["GET"])
def session_stats():
    """Get session statistics"""
    try:
        session_id = get_or_create_session_id()
        history = get_conversation_history(session_id)
        points = get_user_plotted_points(session_id)
        total_distance = calculate_total_route_distance(points)
        
        return jsonify({
            "session_id": session_id,
            "conversation_count": len(history),
            "plotted_points": len(points),
            "total_distance_km": round(total_distance, 2),
            "session_created": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def serve_index():
    """Serve the main application page with injected API keys"""
    try:
        # Try to read from static folder
        static_path = os.path.join(app.static_folder or 'frontend', 'index.html')
        
        if os.path.exists(static_path):
            with open(static_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            # Fallback: try current directory
            with open('index.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
        
        # Replace API key placeholders with actual keys
        replacements = {
            "const GOOGLE_MAPS_API_KEY = 'YOUR_GOOGLE_MAPS_API_KEY';": f"const GOOGLE_MAPS_API_KEY = '{MAPS_API_KEY or ''}';",
            "const PLACES_API_KEY = 'YOUR_PLACES_API_KEY';": f"const PLACES_API_KEY = '{PLACES_API_KEY or ''}';",
            "const DIRECTIONS_API_KEY = 'YOUR_DIRECTIONS_API_KEY';": f"const DIRECTIONS_API_KEY = '{DIRECTIONS_API_KEY or ''}';",
            "const ROUTES_API_KEY = 'YOUR_ROUTES_API_KEY';": f"const ROUTES_API_KEY = '{ROUTES_API_KEY or ''}';",
        }
        
        for placeholder, replacement in replacements.items():
            html_content = html_content.replace(placeholder, replacement)
        
        return render_template_string(html_content)
        
    except FileNotFoundError:
        return jsonify({
            "error": "index.html not found", 
            "help": "Make sure index.html is in the frontend folder or current directory"
        }), 404
    except Exception as e:
        print(f"Error serving index: {e}")
        return jsonify({"error": "Failed to serve application"}), 500

@app.route("/<path:path>")
def serve_static(path):
    """Serve static files"""
    try:
        return send_from_directory(app.static_folder or 'frontend', path)
    except:
        return jsonify({"error": "File not found"}), 404

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    print("SafePath Backend Starting...")
    print(f"OpenAI API Key: {'✓' if client.api_key else '✗'}")
    print(f"GNews API Key: {'✓' if GNEWS_API_KEY else '✗'}")
    print(f"Google Maps API Key: {'✓' if MAPS_API_KEY else '✗'}")
    print(f"Places API Key: {'✓' if PLACES_API_KEY else '✗'}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)