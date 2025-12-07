# InfoHub AI Tax Advisor - Frontend

Next.js 14 frontend application for InfoHub AI Tax Advisor.

## Features

- 🎨 Modern UI with TailwindCSS
- 💬 Real-time chat interface
- 🔐 JWT-based authentication
- 📱 Responsive design
- 🌐 TypeScript for type safety

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser.

### Environment Variables

Create `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Project Structure

```
frontend/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Home page
│   └── globals.css        # Global styles
├── components/            # React components
├── lib/                   # Utilities and helpers
├── public/               # Static assets
└── package.json          # Dependencies
```

## Development

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint

## Deployment

### Docker

```bash
# Build Docker image
docker build -f docker/frontend.Dockerfile -t infohub-frontend .

# Run container
docker run -p 3000:3000 infohub-frontend
```

### Vercel

The easiest way to deploy is using the [Vercel Platform](https://vercel.com).

## Technologies

- **Next.js 14** - React framework
- **TypeScript** - Type safety
- **TailwindCSS** - Utility-first CSS
- **Axios** - HTTP client
- **Zustand** - State management
- **React Markdown** - Markdown rendering
