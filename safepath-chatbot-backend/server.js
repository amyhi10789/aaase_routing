const express = require('express');
const axios = require('axios');
const OpenAI = require('openai');
const cors = require('cors');
require('dotenv').config();

const app = express();
const port = 5000;

app.use(cors());
app.use(express.json());

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

async function reverseGeocode(lat, lng) {
  try {
    const response = await axios.get(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`
    );
    const address = response.data.address;
    return address.city || address.town || address.village || address.county || 'unknown location';
  } catch (error) {
    console.error('Geocoding error:', error.message);
    return 'unknown location';
  }
}

async function fetchNews(location) {
  try {
    const query = `crime OR safety in ${location}`;
    const response = await axios.get('https://gnews.io/api/v4/search', {
      params: {
        q: query,
        lang: 'en',
        country: 'us', 
        max: 5,
        apikey: process.env.GNEWS_API_KEY,
      },
    });
    return response.data.articles.map(article => ({
      title: article.title,
      description: article.description,
      url: article.url,
      publishedAt: article.publishedAt,
    }));
  } catch (error) {
    console.error('GNews API error:', error.message);
    return [];
  }
}

app.post('/api/chat', async (req, res) => {
  const { message, lat, lng } = req.body;

  if (!message || !lat || !lng) {
    return res.status(400).json({ error: 'Message, latitude, and longitude are required' });
  }

  try {
    // step 1: reversing the geocode to get the location
    const location = await reverseGeocode(lat, lng);

    // step 2: fetching relevant news articles
    const newsArticles = await fetchNews(location);

    // step 3: preparing the prompt for OpenAI
    const systemPrompt = `
      You are a chatbot embedded in a website featuring a visualized world map that guides users through safe paths in a city.
      Your role is to answer questions about violent crime (e.g., recent news, overall statistics) and general safety tips for the user's geolocated area: ${location}.
      Use the following recent news articles for context (if relevant):
      ${JSON.stringify(newsArticles, null, 2)}
      If the user asks about anything unrelated to crime or safety, respond with: "I'm sorry, I can only answer questions related to crime and safety in your area."
      Provide concise, accurate, and helpful responses.
    `;

    const completion = await openai.chat.completions.create({
      model: 'gpt-4.1-mini',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: message },
      ],
      max_tokens: 150, 
      temperature: 0.7,
    });

    const responseText = completion.choices[0].message.content;

    res.json({ response: responseText });
  } catch (error) {
    console.error('Error processing chat request:', error.message);
    res.status(500).json({ response: 'Sorry, something went wrong. Try again later.' });
  }
});

app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});