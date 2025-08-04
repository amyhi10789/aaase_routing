const express = require('express');
const bodyParser = require('body-parser');
const chatRoute = require('./routes/chat');
const cors = require('cors');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(bodyParser.json());
app.use('/api/chat', chatRoute);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`SafePath backend running on port ${PORT}`);
});