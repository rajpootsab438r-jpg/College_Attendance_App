const CACHE_NAME = 'cukur-attendance-v3';
const OFFLINE_ASSETS = [
  '/',
  '/login/admin',
  '/login/teacher',
  '/admin/dashboard',
  '/teacher/dashboard'
];

// Offline rehne par static screens background pipelines block nahi karengi
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(OFFLINE_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Network intercept function: agar offline ho to error page ki jagah cached content server show karega
self.addEventListener('fetch', (event) => {
  if (event.request.method === 'GET') {
    event.respondWith(
      fetch(event.request).then((networkResponse) => {
        return caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, networkResponse.clone());
          return networkResponse;
        });
      }).catch(() => {
        return caches.match(event.request).then((cachedResponse) => {
          return cachedResponse || caches.match('/');
        });
      })
    );
  }
});
