# Deploying Path Pal to Render

This guide will help you deploy Path Pal to Render.

## Prerequisites

1. A GitHub account
2. A Render account (sign up at https://render.com)
3. Your OpenAI API key

## Deployment Steps

### 1. Push to GitHub

First, commit and push your code to a GitHub repository:

```bash
git add .
git commit -m "Initial commit - Path Pal PWA"
git remote add origin <your-github-repo-url>
git push -u origin main
```

### 2. Create a New Web Service on Render

1. Log in to your Render dashboard
2. Click "New +" and select "Web Service"
3. Connect your GitHub repository
4. Render will detect the `render.yaml` file automatically

### 3. Configure Environment Variables

1. In your Render service dashboard, go to "Environment"
2. Add the following environment variable:
   - **Key**: `GPT_API_KEY`
   - **Value**: Your OpenAI API key (from gpt-key.txt)
   - Make sure to mark it as "Secret"

### 4. Deploy

1. Render will automatically start building and deploying
2. The build command is: `npm install`
3. The start command is: `npm start`
4. Wait for deployment to complete

### 5. Access Your App

Once deployed, your app will be available at:
- `https://path-pal.onrender.com` (or your custom domain)

## Configuration

### Automatic Deployment

Render will automatically redeploy when you push to your main branch (if connected to GitHub).

### Custom Domain

To add a custom domain:
1. Go to Settings > Custom Domains
2. Add your domain
3. Follow Render's DNS configuration instructions

### Environment Variables

All sensitive data should be set as environment variables in Render:
- `GPT_API_KEY`: Your OpenAI API key (required for AI features)

### Health Check

The app includes a `/health` endpoint that Render can use for health checks.

## Troubleshooting

### Build Fails

- Check that all dependencies are in `package.json`
- Ensure Node.js version is compatible (18+)

### App Won't Start

- Check the logs in Render dashboard
- Verify `GPT_API_KEY` is set correctly
- Ensure port is using `process.env.PORT` (already configured)

### API Calls Fail

- Verify `GPT_API_KEY` is set in environment variables
- Check that the API key is valid and has credits

## Notes

- The free tier on Render spins down after 15 minutes of inactivity
- First request after spin-down may take 30-60 seconds
- For production use, consider upgrading to a paid plan
- Keep your API key secure - never commit it to git

