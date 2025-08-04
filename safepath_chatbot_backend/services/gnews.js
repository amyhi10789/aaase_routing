const axios = require('axios');

async function getCrimeNews(lat, lng) {
  const query = `crime OR shooting OR robbery near ${lat},${lng}`;
  const url = `https://gnews.io/api/v4/search?q=${encodeURIComponent(query)}&lang=en&max=5&token=${process.env.GNEWS_API_KEY}`;

  const res = await axios.get(url);
  return res.data.articles.map(a => `${a.title} - ${a.description}`).join('\n');
}

module.exports = { getCrimeNews };
