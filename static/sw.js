const CACHE_NAME = 'college-attendance-v5';
const CACHE_PREFIX = 'college-attendance-';
const OFFLINE_URL = '/offline';
const SYNC_TAG = 'sync-cukur-data';
const DB_NAME = 'college-attendance-offline';
const DB_VERSION = 1;
const STORE_NAME = 'pending';
const APP_PATHS = new Set([
  '/',
  '/login/admin',
  '/login/teacher',
  '/login/developer',
  '/admin/dashboard',
  '/developer/dashboard',
  '/teacher/dashboard'
]);
const PRECACHE_URLS = [
  '/',
  '/offline',
  '/manifest.json',
  '/login/admin',
  '/login/teacher',
  '/login/developer',
  '/static/offline-sync.js',
  '/static/icon.svg'
];

let syncPromise = null;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.add(OFFLINE_URL);
    await Promise.allSettled(PRECACHE_URLS
      .filter((url) => url !== OFFLINE_URL)
      .map((url) => cache.add(url)));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
    await registerBackgroundSync();
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname === '/logout') {
    event.respondWith((async () => {
      const response = await fetch(request);
      await clearPrivatePages();
      return response;
    })());
    return;
  }

  if (request.mode === 'navigate' && APP_PATHS.has(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.json') {
    event.respondWith(cacheFirst(request));
  }
});

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await findCachedPage(cache, request);
  const update = fetch(request).then(async (response) => {
    const responseUrl = new URL(response.url || request.url);
    const isHtml = response.headers.get('content-type')?.includes('text/html');
    if (response.ok && isHtml && responseUrl.pathname === new URL(request.url).pathname) {
      await cache.put(request, response.clone());
    }
    return response;
  });

  if (cached) {
    update.catch((error) => console.warn('Offline page refresh failed:', error));
    return cached;
  }

  try {
    return await update;
  } catch (error) {
    console.warn('Page is unavailable online; serving offline fallback:', error);
    return (await cache.match(OFFLINE_URL)) || unavailableResponse();
  }
}

async function findCachedPage(cache, request) {
  const exact = await cache.match(request);
  if (exact) {
    return exact;
  }
  const pathname = new URL(request.url).pathname;
  const matchingRequest = (await cache.keys()).find((cachedRequest) =>
    new URL(cachedRequest.url).pathname === pathname);
  return matchingRequest ? cache.match(matchingRequest) : undefined;
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) {
    fetch(request).then((response) => {
      if (response.ok) {
        return cache.put(request, response.clone());
      }
      return undefined;
    }).catch((error) => console.warn('Cached asset refresh failed:', error));
    return cached;
  }

  try {
    const response = await fetch(request);
    if (response.ok) {
      await cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.warn('Asset is not cached:', error);
    return unavailableResponse();
  }
}

function unavailableResponse() {
  return new Response('This page or resource has not been cached yet. Connect to the internet and open it once.', {
    status: 503,
    headers: { 'Content-Type': 'text/plain; charset=utf-8' }
  });
}

async function clearPrivatePages() {
  const cache = await caches.open(CACHE_NAME);
  const requests = await cache.keys();
  await Promise.all(requests.map((request) => {
    const pathname = new URL(request.url).pathname;
    if (pathname === '/admin/dashboard' ||
        pathname === '/developer/dashboard' ||
        pathname === '/teacher/dashboard') {
      return cache.delete(request);
    }
    return Promise.resolve(false);
  }));
}

function openQueueDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Could not open offline queue.'));
  });
}

function readPendingOperations(database) {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, 'readonly');
    const request = transaction.objectStore(STORE_NAME).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Could not read offline queue.'));
  });
}

function removePendingOperation(database, id) {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, 'readwrite');
    transaction.objectStore(STORE_NAME).delete(id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error('Could not update offline queue.'));
    transaction.onabort = () => reject(transaction.error || new Error('Offline queue update was aborted.'));
  });
}

function allowedQueueUrl(value) {
  let url;
  try {
    url = new URL(value, self.location.origin);
  } catch (error) {
    return false;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return false;
  }
  return url.pathname === '/teacher/quick_attendance' ||
    url.pathname === '/admin/dashboard' ||
    url.pathname === '/admin/import_students' ||
    url.pathname === '/developer/dashboard' ||
    url.pathname === '/developer/create_college' ||
    /^\/developer\/delete\/(college|teacher|student)\/\d+$/.test(url.pathname);
}

async function notifyClients(message) {
  const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  clients.forEach((client) => client.postMessage(message));
}

async function runQueue() {
  if (syncPromise) {
    return syncPromise;
  }

  syncPromise = (async () => {
    const database = await openQueueDatabase();
    try {
      const pending = await readPendingOperations(database);
      for (const operation of pending) {
        if (!allowedQueueUrl(operation.url) ||
            operation.method !== 'POST' ||
            !operation.operationId ||
            !operation.actor) {
          throw new Error('An offline action has invalid routing or identity data; it was kept for review.');
        }

        const queuePath = new URL(operation.url, self.location.origin);
        const response = await fetch(queuePath.pathname + queuePath.search, {
          method: 'POST',
          credentials: 'include',
          cache: 'no-store',
          headers: {
            'Content-Type': operation.contentType,
            'Accept': 'application/json',
            'X-Offline-Sync': '1',
            'X-Sync-Operation': operation.operationId,
            'X-Sync-Actor': operation.actor
          },
          body: operation.body
        });
        if (!response.ok) {
          throw new Error(`Sync rejected with HTTP ${response.status}; pending data was retained.`);
        }
        const result = await response.json();
        if (result.status !== 'success') {
          throw new Error(result.message || 'Server did not confirm the offline action.');
        }

        await removePendingOperation(database, operation.id);
        await notifyClients({ type: 'OFFLINE_SYNC_COMPLETE', id: operation.id });
      }
      await notifyClients({ type: 'OFFLINE_SYNC_IDLE' });
    } catch (error) {
      await notifyClients({
        type: 'OFFLINE_SYNC_FAILED',
        message: error instanceof Error ? error.message : 'Offline sync failed; queued data was retained.'
      });
      throw error;
    } finally {
      database.close();
    }
  })().finally(() => {
    syncPromise = null;
  });

  return syncPromise;
}

async function registerBackgroundSync() {
  if (!self.registration.sync) {
    return;
  }
  try {
    await self.registration.sync.register(SYNC_TAG);
  } catch (error) {
    console.warn('Background Sync registration failed:', error);
  }
}

self.addEventListener('sync', (event) => {
  if (event.tag === SYNC_TAG) {
    event.waitUntil(runQueue());
  }
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'QUEUE_SAVED') {
    event.waitUntil(registerBackgroundSync());
  } else if (event.data?.type === 'SYNC_NOW') {
    event.waitUntil(runQueue());
  }
});
