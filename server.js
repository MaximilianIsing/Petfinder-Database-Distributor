const express = require('express');
const path = require('path');
const cors = require('cors');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

// Read GPT key from environment variable (for Render) or file (for local dev)
let GPT_API_KEY = process.env.GPT_API_KEY || '';
if (!GPT_API_KEY) {
  try {
    GPT_API_KEY = fs.readFileSync(path.join(__dirname, 'gpt-key.txt'), 'utf8').trim();
  } catch (error) {
    console.error('Warning: GPT API key not found in environment or file');
  }
}

// API endpoint for GPT requests
app.post('/api/chat', async (req, res) => {
  try {
    const { message, context } = req.body;
    
    if (!GPT_API_KEY) {
      return res.status(500).json({ error: 'GPT API key not configured' });
    }

    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${GPT_API_KEY}`
      },
      body: JSON.stringify({
        model: 'gpt-4',
        messages: [
          {
            role: 'system',
            content: 'You are a helpful college admissions counselor and academic advisor. Provide personalized, actionable advice for students planning their college path.'
          },
          ...(context || []),
          {
            role: 'user',
            content: message
          }
        ],
        temperature: 0.7,
        max_tokens: 1000
      })
    });

    const data = await response.json();
    
    if (!response.ok) {
      return res.status(response.status).json({ error: data.error?.message || 'API error' });
    }

    res.json({ 
      message: data.choices[0].message.content,
      usage: data.usage
    });
  } catch (error) {
    console.error('GPT API error:', error);
    res.status(500).json({ error: 'Failed to process request' });
  }
});

// Serve all HTML pages
const htmlPages = [
  'index.html', 'profile.html', 'odds.html', 'simulator.html', 
  'explorer.html', 'career.html', 'activities.html', 'planner.html', 
  'messages.html', 'saved.html'
];

htmlPages.forEach(page => {
  app.get(`/${page}`, (req, res) => {
    res.sendFile(path.join(__dirname, page));
  });
  
  // Also handle without .html extension
  const route = page.replace('.html', '');
  if (route !== 'index') {
    app.get(`/${route}`, (req, res) => {
      res.sendFile(path.join(__dirname, page));
    });
  }
});

// Serve index.html for root route
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Health check endpoint for Render
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Path Pal server running on port ${PORT}`);
  if (GPT_API_KEY) {
    console.log('GPT API key configured');
  } else {
    console.warn('Warning: GPT API key not configured. AI features will not work.');
  }
});

