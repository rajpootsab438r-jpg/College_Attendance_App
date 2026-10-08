const CACHE_NAME = 'college-attendance-v1';
const OFFLINE_URL = '/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.add(OFFLINE_URL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((key) => key.startsWith('college-attendance-') && key !== CACHE_NAME)
        .map((key) => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'GET' || url.origin !== self.location.origin || request.mode !== 'navigate') {
    return;
  }

  event.respondWith((async () => {
    try {
      const response = await fetch(request);
      if (response.ok && response.headers.get('content-type')?.includes('text/html')) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(request, response.clone());
      }
      return response;
    } catch {
      const cachedPage = await caches.match(request);
      return cachedPage || caches.match(OFFLINE_URL);
    }
  })());
});