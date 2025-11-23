# Path Pal

**v1.09.1**

Path Pal is a Progressive Web App (PWA) that helps students plan their college journey with personalized recommendations, admission odds calculations, and AI-powered guidance.

## Features

- **Home Page**: Quick access to all features with progress tracking
- **My Profile**: Manage academic information, test scores, and intended majors
- **Admissions Odds**: See your acceptance probability for saved colleges with AI tips
- **"What If" Simulator**: Test hypothetical changes to see how they affect admission odds
- **College Explorer**: Discover and filter colleges with AI recommendations
- **Career & Salary Paths**: Explore career outcomes and median salaries by major
- **Activity & Internship Recs**: Get personalized activity and internship suggestions
- **4-Year Planner**: Step-by-step roadmap for courses, activities, and milestones
- **Messages/AI Chat Advisor**: 24/7 AI counselor for instant guidance
- **Saved Colleges**: Bookmark colleges and track application progress

## Installation

### Local Development

1. Install dependencies:
```bash
npm install
```

2. Set up your OpenAI API key (choose one method):
   - **Option A**: Create a `gpt-key.txt` file with your API key
   - **Option B**: Set the `GPT_API_KEY` environment variable

3. Start the server:
```bash
npm start
```

The server will run on `http://localhost:3000` (or the port specified in the PORT environment variable).

### Deploying to Render

See [RENDER_DEPLOY.md](./RENDER_DEPLOY.md) for detailed deployment instructions.

Quick steps:
1. Push your code to GitHub
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Set `GPT_API_KEY` environment variable in Render dashboard
5. Deploy!

### Setting Up Custom Domain (pathpal.us)

See [DOMAIN_SETUP.md](./DOMAIN_SETUP.md) for detailed instructions on connecting your GoDaddy domain to Render.

Quick steps:
1. Add custom domain in Render dashboard (Settings → Custom Domains)
2. Configure DNS in GoDaddy (CNAME or A records)
3. Wait for DNS propagation (5-15 minutes)
4. SSL certificate will be automatically provisioned by Render

## Usage

1. Open the application in a mobile browser (or browser mobile view)
2. Complete your profile to get personalized recommendations
3. Explore colleges and save your favorites
4. Use the AI chat advisor for instant guidance
5. Track your progress with the 4-Year Planner

## Technology Stack

- **Frontend**: HTML, CSS (with custom Arvo font), JavaScript
- **Backend**: Node.js with Express
- **AI Integration**: OpenAI GPT-4 API
- **PWA**: Service Worker and Web App Manifest
- **Storage**: LocalStorage for offline data persistence

## Color Scheme

- Primary Green: `#0d8c79`
- Background: White (`#ffffff`)
- Light Mint: `#e8f5f3`
- Text Dark: `#2c3e50`
- Text Light: `#7f8c8d`

## Mobile-First Design

Path Pal is designed for mobile devices. Desktop users will see a message prompting them to use a mobile device for the best experience.

## Environment Variables

For production deployment (Render), set:
- `GPT_API_KEY`: Your OpenAI API key (required for AI features)
- `PORT`: Server port (optional, defaults to 3000)
- `NODE_ENV`: Set to `production` for production

See `env.example.txt` for a template.

## License

ISC

---

**Note**: This is a PWA that works offline after the first load. Make sure to keep your GPT API key secure and never commit it to version control. The `gpt-key.txt` file is already in `.gitignore`.

