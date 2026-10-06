const CACHE_NAME = 'cukur-cache-v1';
const ASSETS = [
  '/',
  '/login/admin',
  '/login/teacher',
  '/admin/dashboard',
  '/teacher/dashboard'
];

// Offline rehne par screens ko cache se open rakhna
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)));
});

self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then(cachedResponse => {
      return cachedResponse || fetch(e.request);
    }).catch(() => caches.match('/'))
  );
});

// Online aate hi dynamic local data background sync trigger karna
self.addEventListener('sync', (e) => {
  if (e.tag === 'sync-attendance') {
    e.waitUntil(syncOfflineDataToServer());
  }
});
