const express = require('express');
const router = express.Router();
const { getCrimeNews } = require('../services/gnews');
const { getAIResponse } = require('../services/openai');

router.post('/', async (req, res) => {
  const { message, lat, lng } = req.body;

  try {
    const news = await getCrimeNews(lat, lng);
    const aiResponse = await getAIResponse(message, news);

    res.json({ response: aiResponse });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Error handling chat request' });
  }
});

module.exports = router;
