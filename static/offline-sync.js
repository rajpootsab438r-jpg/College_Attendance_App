(function () {
  'use strict';

  const DB_NAME = 'college-attendance-offline';
  const DB_VERSION = 1;
  const STORE_NAME = 'pending';
  const SYNC_TAG = 'sync-cukur-data';

  let databasePromise;

  function openDatabase() {
    if (!databasePromise) {
      databasePromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = () => {
          const database = request.result;
          if (!database.objectStoreNames.contains(STORE_NAME)) {
            database.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error('Could not open offline storage.'));
      });
    }
    return databasePromise;
  }

  function createOperationId() {
    return window.crypto?.randomUUID
      ? window.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  async function countPending() {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, 'readonly');
      const request = transaction.objectStore(STORE_NAME).count();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('Could not read pending changes.'));
    });
  }

  async function enqueue(url, body, contentType, tag, operationId) {
    const actor = document.body.dataset.offlineActor;
    if (!actor) {
      throw new Error('Offline sync identity is not configured for this page.');
    }

    const database = await openDatabase();
    const entry = {
      url: new URL(url, location.origin).href,
      method: 'POST',
      body,
      contentType,
      actor,
      operationId,
      tag,
      createdAt: new Date().toISOString()
    };
    const id = await new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      const request = transaction.objectStore(STORE_NAME).add(entry);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('Could not save the offline change.'));
    });

    const registration = await navigator.serviceWorker?.ready;
    if (!registration) {
      throw new Error('Service worker is not ready; the change remains in this device storage.');
    }

    if (registration.sync) {
      try {
        await registration.sync.register(SYNC_TAG);
      } catch (error) {
        console.warn('Background Sync registration failed; will retry when online.', error);
      }
    }
    registration.active?.postMessage({ type: 'QUEUE_SAVED' });
    updatePendingCount();
    return id;
  }

  async function sendOrQueue(url, body, contentType, tag) {
    const actor = document.body.dataset.offlineActor;
    if (!actor) {
      throw new Error('Offline sync identity is not configured for this page.');
    }
    const operationId = createOperationId();
    if (!navigator.onLine) {
      return { queued: true, id: await enqueue(url, body, contentType, tag, operationId) };
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': contentType,
          'Accept': 'application/json',
          'X-Offline-Sync': '1',
          'X-Sync-Operation': operationId,
          'X-Sync-Actor': actor
        },
        body
      });
      const result = await response.json().catch(() => null);
      if (!response.ok || !result || result.status !== 'success') {
        throw new Error(result?.message || `The server rejected the change (HTTP ${response.status}).`);
      }
      return { queued: false, result };
    } catch (error) {
      if (!navigator.onLine || error instanceof TypeError) {
        return { queued: true, id: await enqueue(url, body, contentType, tag, operationId) };
      }
      throw error;
    }
  }

  function statusElement() {
    let status = document.getElementById('offline-sync-status');
    if (!status) {
      status = document.createElement('div');
      status.id = 'offline-sync-status';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      status.style.cssText = 'position:sticky;top:0;z-index:10001;padding:10px 14px;margin-bottom:12px;border-radius:6px;background:#fff3cd;color:#664d03;font-weight:600;';
      document.body.prepend(status);
    }
    return status;
  }

  async function updatePendingCount(message) {
    try {
      const pending = await countPending();
      const status = statusElement();
      if (message) {
        status.textContent = message;
      } else if (pending > 0) {
        status.textContent = `${pending} change(s) saved on this device and waiting to sync.`;
      } else {
        status.textContent = '';
        status.style.display = 'none';
      }
      if (message) {
        status.style.display = 'block';
      }
    } catch (error) {
      console.error('Could not display offline queue status:', error);
    }
  }

  function actionTag(formData, pathname) {
    if (pathname === '/teacher/quick_attendance') return 'pending_attendance';
    if (pathname === '/admin/import_students') return 'pending_student_import';
    const action = formData.get('action') || 'mutation';
    return `pending_${String(action).replace(/[^a-z0-9_]+/gi, '_')}`;
  }

  function installFormQueue() {
    document.addEventListener('submit', async (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || form.method.toUpperCase() !== 'POST') {
        return;
      }

      const endpoint = new URL(form.action || location.href, location.href);
      if (endpoint.origin !== location.origin) {
        return;
      }

      event.preventDefault();
      const submitter = event.submitter;
      const formData = new FormData(form);
      if (submitter?.name) {
        formData.append(submitter.name, submitter.value);
      }
      const body = new URLSearchParams(formData);
      const button = submitter instanceof HTMLButtonElement ? submitter : form.querySelector('button[type="submit"], button:not([type])');
      if (button) button.disabled = true;

      try {
        const result = await sendOrQueue(endpoint.href, body.toString(), 'application/x-www-form-urlencoded;charset=UTF-8', actionTag(formData, endpoint.pathname));
        if (result.queued) {
          updatePendingCount('Saved on this device. It will sync automatically when the connection returns and this account is authenticated.');
          return;
        }
        location.reload();
      } catch (error) {
        updatePendingCount(error instanceof Error ? error.message : 'Could not save this change.');
      } finally {
        if (button) button.disabled = false;
      }
    });
  }

  async function requestSync() {
    if (!navigator.onLine) return;
    try {
      const registration = await navigator.serviceWorker?.ready;
      if (!registration) return;
      if (registration.sync) {
        try {
          await registration.sync.register(SYNC_TAG);
        } catch (error) {
          console.warn('Background Sync registration failed; using online retry.', error);
        }
      }
      registration.active?.postMessage({ type: 'SYNC_NOW' });
    } catch (error) {
      console.error('Could not start automatic offline sync:', error);
    }
  }

  window.OfflineSync = {
    enqueue,
    sendOrQueue,
    updatePendingCount,
    requestSync
  };

  if (document.body.dataset.offlineQueueForms === 'true') {
    installFormQueue();
  }
  window.addEventListener('online', requestSync);
  navigator.serviceWorker?.addEventListener('message', (event) => {
    if (event.data?.type === 'OFFLINE_SYNC_COMPLETE' || event.data?.type === 'OFFLINE_SYNC_IDLE') {
      updatePendingCount();
    } else if (event.data?.type === 'OFFLINE_SYNC_FAILED') {
      updatePendingCount(event.data.message);
    }
  });
  window.addEventListener('load', () => {
    updatePendingCount();
    requestSync();
  });
})();
