const { OpenAI } = require('openai');

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

async function getAIResponse(userMessage, crimeContext) {
  const chat = await openai.chat.completions.create({
    model: "gpt-4.0-turbo", // or "gpt-4.5-turbo" if you have access
    messages: [
      { role: "system", content: "You're a helpful safety assistant. Use the local crime info when helpful." },
      { role: "user", content: `Here's recent news:\n${crimeContext}` },
      { role: "user", content: userMessage }
    ],
  });

  return chat.choices[0].message.content;
}

module.exports = { getAIResponse };