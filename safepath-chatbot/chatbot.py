from flask import Flask, request, jsonify, send_from_directory, session, render_template_string
from flask_cors import CORS
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv
import uuid
from datetime import datetime

load_dotenv()

app = Flask(__name__, static_folder="frontend", static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")  # Add this to your .env file
CORS(app, supports_credentials=True)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")
MAPS_API_KEY = os.getenv("MAPS_JAVASCRIPT_KEY")
PLACES_API_KEY = os.getenv("PLACES_KEY")
DIRECTIONS_API_KEY = os.getenv("DIRECTIONS_KEY")
ROUTES_API_KEY = os.getenv("ROUTES_KEY")

# Store conversation history (in production, use Redis or database)
conversation_history = {}

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

def reverse_geocode(lat, lng):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=10"
        response = requests.get(url, headers={'User-Agent': 'LocationBot/1.0'})
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
            
        return ", ".join(location_parts) if location_parts else "unknown location"
    except Exception as e:
        print("Geocoding error:", str(e))
        return "unknown location"

def get_place_details(place_id):
    """Get detailed information about a place using Google Places API"""
    if not PLACES_API_KEY:
        return None
    
    try:
        url = f"https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_address,geometry,rating,types,photos,reviews',
            'key': PLACES_API_KEY
        }
        
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                return data['result']
        return None
    except Exception as e:
        print(f"Places API error: {e}")
        return None

def search_nearby_places(lat, lng, place_type="point_of_interest", radius=5000):
    """Search for nearby places using Google Places API"""
    if not PLACES_API_KEY:
        return []
    
    try:
        url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            'location': f"{lat},{lng}",
            'radius': radius,
            'type': place_type,
            'key': PLACES_API_KEY
        }
        
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                return data['results'][:10]  # Return top 10 results
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
        
        response = requests.get(url, params=params)
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
        
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Routes API error: {e}")
        return None

def fetch_crime_news(location=None, global_query=None):
    """Fetch recent crime and safety news for a specific location or global query"""
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
        
        for query in search_queries:
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
            
            response = requests.get(url, params=params)
            
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
            else:
                print(f"GNews API error for query '{query}': {response.status_code}")
        
        # Sort by publication date (most recent first) and limit to 10 total
        all_articles.sort(key=lambda x: x["publishedAt"], reverse=True)
        return all_articles[:10]
        
    except Exception as e:
        print("News API error:", str(e))
        return []

def extract_location_from_query(message):
    """Extract location mentions from user queries for global crime questions"""
    message_lower = message.lower()
    
    # Common location patterns
    location_patterns = [
        r'in ([A-Za-z\s]+?)(?:\s|$|[,.])',
        r'from ([A-Za-z\s]+?)(?:\s|$|[,.])',
        r'about ([A-Za-z\s]+?)(?:\s|$|[,.])',
        r'([A-Za-z\s]+?) crime',
        r'([A-Za-z\s]+?) safety',
        r'([A-Za-z\s]+?) statistics'
    ]
    
    # Known cities/countries/regions to look for
    locations = [
        'new york', 'los angeles', 'chicago', 'houston', 'philadelphia',
        'london', 'paris', 'tokyo', 'beijing', 'moscow', 'mumbai',
        'canada', 'mexico', 'brazil', 'argentina', 'uk', 'france', 'germany',
        'italy', 'spain', 'japan', 'china', 'india', 'australia', 'russia',
        'california', 'texas', 'florida', 'new york state'
    ]
    
    for location in locations:
        if location in message_lower:
            return location
    
    import re
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
    
    location_indicators = [
        'in ', 'from ', 'about ', ' crime in ', ' safety in ',
        ' statistics in ', ' news from '
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
    """Format news articles in a structured way for the AI with emphasis on extractable data"""
    if not articles:
        return "No recent crime or safety news found for this location."
    
    formatted_news = f"AVAILABLE NEWS DATA ({len(articles)} articles with extractable statistics and details):\n\n"
    
    for i, article in enumerate(articles, 1):
        # Parse date to make it more readable
        try:
            from datetime import datetime
            pub_date = datetime.fromisoformat(article["publishedAt"].replace('Z', '+00:00'))
            readable_date = pub_date.strftime("%B %d, %Y at %I:%M %p")
            days_ago = (datetime.now(pub_date.tzinfo) - pub_date).days
            recency = f"({days_ago} days ago)" if days_ago > 0 else "(Today)"
        except:
            readable_date = article["publishedAt"]
            recency = ""
        
        formatted_news += f"ARTICLE #{i}:\n"
        formatted_news += f"HEADLINE: \"{article['title']}\"\n"
        formatted_news += f"SOURCE: {article['source']}\n"
        formatted_news += f"PUBLISHED: {readable_date} {recency}\n"
        formatted_news += f"FULL DESCRIPTION: {article['description']}\n"
        formatted_news += f"URL: {article['url']}\n"
        formatted_news += f"SEARCH QUERY USED: {article['query_used']}\n"
        formatted_news += "=" * 80 + "\n\n"
    
    formatted_news += f"""
INSTRUCTIONS FOR USING THIS DATA:
- You can quote exact headlines by using the text after "HEADLINE:"
- You can reference specific statistics, numbers, percentages mentioned in descriptions
- You can mention exact publication dates and sources
- You can tell users about specific incidents described in the articles
- You can provide the URLs if users want to read full articles
- Extract and share any numerical data (crime rates, incident counts, percentages, etc.)

EXAMPLE RESPONSES YOU CAN GIVE:
- "According to a recent article from [Source] published on [Date], titled '[Headline]'..."
- "Based on the statistics in this recent report..."
- "A specific incident reported [X days ago] shows..."
- "The headline '[Exact Headline]' from [Source] indicates..."
"""
    
    return formatted_news

def check_gnews_api_status():
    """Check if GNews API is accessible"""
    if not GNEWS_API_KEY:
        return False, "GNews API key not configured"
    
    try:
        # Test with a simple query
        url = "https://gnews.io/api/v4/search"
        params = {
            "q": "test",
            "lang": "en",
            "max": 1,
            "apikey": GNEWS_API_KEY
        }
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            return True, "API accessible"
        elif response.status_code == 401:
            return False, "Invalid API key"
        elif response.status_code == 429:
            return False, "API rate limit exceeded"
        else:
            return False, f"API error: {response.status_code}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"

def is_crime_or_safety_related(message):
    """Check if the user's message is related to crime or safety (local or global)"""
    message_lower = message.lower()
    
    crime_safety_keywords = [
        'crime', 'crimes', 'criminal', 'safety', 'safe', 'dangerous', 'danger',
        'security', 'violence', 'violent', 'assault', 'robbery', 'theft', 'steal',
        'murder', 'homicide', 'shooting', 'stabbing', 'burglary', 'break-in',
        'vandalism', 'drug', 'drugs', 'gang', 'gangs', 'police', 'arrest',
        'attack', 'mugging', 'fraud', 'scam', 'harassment', 'domestic violence',
        'kidnapping', 'rape', 'sexual assault', 'stalking', 'threats',
        'crime rate', 'crime statistics', 'police report', 'incident',
        'law enforcement', 'criminal activity', 'public safety'
    ]
    
    location_indicators = [
        'here', 'near me', 'nearby', 'in this area', 'around here',
        'in my area', 'my location', 'this location', 'this place',
        'where i am', 'my neighborhood', 'this neighborhood',
        # Global location indicators
        'in ', 'from ', 'about ', 'worldwide', 'globally', 'international',
        'around the world', 'other countries', 'world crime'
    ]
    
    # Check if message contains crime/safety keywords
    has_crime_keywords = any(keyword in message_lower for keyword in crime_safety_keywords)
    
    # Check if message has any location context (local or global)
    has_location_context = any(indicator in message_lower for indicator in location_indicators)
    
    return has_crime_keywords or has_location_context

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message")
    lat = data.get("lat")
    lng = data.get("lng")

    if not message or lat is None or lng is None:
        return jsonify({"error": "Message, latitude, and longitude are required"}), 400

    try:
        location = reverse_geocode(lat, lng)
        
        if not is_crime_or_safety_related(message):
            return jsonify({"response": "I'm sorry, I can only answer questions related to crime and safety in your area. Please ask about local crime statistics, safety concerns, or security issues."}), 200
        
        # Get crime and safety related news
        crime_articles = fetch_crime_news(location)
        formatted_articles = format_news_for_ai(crime_articles)

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

Recent crime and safety news for {location}:
{formatted_articles}

Always reference the specific location ({location}) in your responses when relevant.
Provide helpful, accurate, and location-specific crime and safety information.
If you don't have specific crime data about their exact location, acknowledge this and provide general safety guidance for similar areas.
Keep responses focused strictly on crime and safety topics.
Keep your responses short - always make sure they're under 100 words.
Don't use too many buzzwords - make it sound human.
Be polite to the user.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=150,
            temperature=0.7
        )

        reply = response.choices[0].message.content
        return jsonify({"response": reply})

    except Exception as e:
        print("Error processing chat request:", str(e))
        return jsonify({"response": "Sorry, something went wrong. Try again later."}), 500

@app.route("/api/places/search", methods=["POST"])
def search_places():
    """Search for places using Google Places API"""
    data = request.get_json()
    query = data.get("query")
    lat = data.get("lat")
    lng = data.get("lng")
    
    if not query:
        return jsonify({"error": "Query is required"}), 400
    
    try:
        places = search_nearby_places(lat or 0, lng or 0, query)
        return jsonify({"places": places})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/places/details", methods=["POST"])
def place_details():
    """Get place details using Google Places API"""
    data = request.get_json()
    place_id = data.get("place_id")
    
    if not place_id:
        return jsonify({"error": "Place ID is required"}), 400
    
    try:
        details = get_place_details(place_id)
        if details:
            return jsonify({"place": details})
        else:
            return jsonify({"error": "Place not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/directions", methods=["POST"])
def directions():
    """Get directions using Google Directions API"""
    data = request.get_json()
    origin = data.get("origin")
    destination = data.get("destination")
    mode = data.get("mode", "driving")
    
    if not origin or not destination:
        return jsonify({"error": "Origin and destination are required"}), 400
    
    try:
        directions_result = get_directions(origin, destination, mode)
        if directions_result:
            return jsonify(directions_result)
        else:
            return jsonify({"error": "Directions not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/routes", methods=["POST"])
def routes():
    """Get routes using Google Routes API"""
    data = request.get_json()
    origin = data.get("origin")
    destination = data.get("destination")
    travel_mode = data.get("travel_mode", "DRIVE")
    
    if not origin or not destination:
        return jsonify({"error": "Origin and destination are required"}), 400
    
    try:
        routes_result = get_routes(origin, destination, travel_mode)
        if routes_result:
            return jsonify(routes_result)
        else:
            return jsonify({"error": "Routes not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/news-status", methods=["GET"])
def news_status():
    try:
        accessible, status = check_gnews_api_status()
        return jsonify({
            "accessible": accessible,
            "status": status,
            "api_key_configured": bool(GNEWS_API_KEY)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/test-news", methods=["POST"])
def test_news():
    try:
        data = request.get_json()
        location = data.get("location", "test location")
        articles = fetch_crime_news(location)
        formatted = format_news_for_ai(articles)
        return jsonify({
            "location": location,
            "articles_found": len(articles),
            "formatted_news": formatted,
            "raw_articles": articles
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/clear-history", methods=["POST"])
def clear_history():
    try:
        session_id = session.get('session_id')
        if session_id and session_id in conversation_history:
            del conversation_history[session_id]
        return jsonify({"message": "Conversation history cleared"})
    except Exception as e:
        return jsonify({"error": "Failed to clear history"}), 500

@app.route("/")
def serve_index():
    # Read the HTML file and inject all API keys
    try:
        with open(os.path.join(app.static_folder, 'index.html'), 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Replace all API key placeholders with actual keys from environment
        replacements = {
            "const GOOGLE_MAPS_API_KEY = 'MAPS_JAVASCRIPT_KEY';": f"const GOOGLE_MAPS_API_KEY = '{MAPS_API_KEY or ''}';",
            "const PLACES_API_KEY = 'PLACES_API_KEY';": f"const PLACES_API_KEY = '{PLACES_API_KEY or ''}';",
            "const DIRECTIONS_API_KEY = 'DIRECTIONS_API_KEY';": f"const DIRECTIONS_API_KEY = '{DIRECTIONS_API_KEY or ''}';",
            "const ROUTES_API_KEY = 'ROUTES_API_KEY';": f"const ROUTES_API_KEY = '{ROUTES_API_KEY or ''}';"
        }
        
        for placeholder, replacement in replacements.items():
            html_content = html_content.replace(placeholder, replacement)
        
        return render_template_string(html_content)
    except Exception as e:
        print(f"Error serving index: {e}")
        return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    app.run(port=5000, debug=True)