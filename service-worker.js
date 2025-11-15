const CACHE_NAME = 'path-pal-v1';
const urlsToCache = [
  '/',
  '/index.html',
  '/profile.html',
  '/odds.html',
  '/simulator.html',
  '/explorer.html',
  '/career.html',
  '/activities.html',
  '/planner.html',
  '/messages.html',
  '/saved.html',
  '/css/style.css',
  '/js/app.js',
  '/js/api.js',
  '/manifest.json',
  '/media/logo/logo256x256.png',
  '/fonts/Arvo/Arvo-Regular.ttf',
  '/fonts/Arvo/Arvo-Bold.ttf'
];

// Install service worker
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(urlsToCache);
      })
  );
});

// Fetch event
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        // Return cached version or fetch from network
        return response || fetch(event.request);
      })
  );
});

// Activate event
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

