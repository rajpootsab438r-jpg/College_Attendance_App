(function () {
  'use strict';

  const DB_NAME = 'college-attendance-offline';
  const DB_VERSION = 5;
  const STORE_NAME = 'pending';
  const ATTENDANCE_STORE = 'pending_attendance';
  const SNAPSHOT_STORE = 'snapshots';
  const SEED_STORE = 'seedData';
  const PROFILE_STORE = 'offlineProfiles';
  const OFFLINE_SESSION_STORE = 'offlineSessions';
  const SYNC_TAG = 'sync-cukur-data';
  const OFFLINE_PROFILE_MAX_AGE = 24 * 60 * 60 * 1000;
  const QUEUE_PATHS = new Set([
    '/teacher/quick_attendance',
    '/admin/dashboard',
    '/admin/import_students',
    '/developer/dashboard',
    '/developer/create_college'
  ]);

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
          if (!database.objectStoreNames.contains(SNAPSHOT_STORE)) {
            database.createObjectStore(SNAPSHOT_STORE, { keyPath: 'cacheKey' });
          }
          if (!database.objectStoreNames.contains(SEED_STORE)) {
            database.createObjectStore(SEED_STORE, { keyPath: 'cacheKey' });
          }
          if (!database.objectStoreNames.contains(PROFILE_STORE)) {
            database.createObjectStore(PROFILE_STORE, { keyPath: 'profileKey' });
          }
          if (!database.objectStoreNames.contains(ATTENDANCE_STORE)) {
            database.createObjectStore(ATTENDANCE_STORE, { keyPath: 'id', autoIncrement: true });
          }
          if (!database.objectStoreNames.contains(OFFLINE_SESSION_STORE)) {
            database.createObjectStore(OFFLINE_SESSION_STORE, { keyPath: 'sessionKey' });
          }
        };
        request.onsuccess = () => {
          request.result.onversionchange = () => {
            request.result.close();
            databasePromise = null;
          };
          resolve(request.result);
        };
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

  function allowedQueueUrl(value) {
    let url;
    try {
      url = new URL(value, location.origin);
    } catch (error) {
      return null;
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }
    if (QUEUE_PATHS.has(url.pathname) ||
        /^\/developer\/delete\/(college|teacher|student)\/\d+$/.test(url.pathname)) {
      return `${url.pathname}${url.search}`;
    }
    return null;
  }

  async function countPending() {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction([STORE_NAME, ATTENDANCE_STORE], 'readonly');
      let total = 0;
      for (const storeName of [STORE_NAME, ATTENDANCE_STORE]) {
        const request = transaction.objectStore(storeName).count();
        request.onsuccess = () => {
          total += request.result;
        };
        request.onerror = () => reject(request.error || new Error('Could not read pending changes.'));
      }
      transaction.oncomplete = () => resolve(total);
      transaction.onerror = () => reject(transaction.error || new Error('Could not read pending changes.'));
    });
  }

  async function storeRecord(storeName, record) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readwrite');
      transaction.objectStore(storeName).put(record);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error || new Error('Could not save offline data.'));
      transaction.onabort = () => reject(transaction.error || new Error('Offline data save was aborted.'));
    });
  }

  async function readRecord(storeName, key) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readonly');
      const request = transaction.objectStore(storeName).get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error || new Error('Could not read offline data.'));
    });
  }

  async function saveSnapshot(cacheKey, data) {
    await storeRecord(SNAPSHOT_STORE, { cacheKey, data, savedAt: Date.now() });
  }

  async function getSnapshot(cacheKey) {
    const record = await readRecord(SNAPSHOT_STORE, cacheKey);
    return record ? record.data : null;
  }

  function seedCacheKey() {
    const collegeId = document.body.dataset.offlineCollege;
    if (!collegeId) {
      throw new Error('Offline attendance data is not linked to a college.');
    }
    return `college-seed:${collegeId}`;
  }

  async function hydrateSeedData() {
    const response = await fetch('/api/offline_seed_data', {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Accept': 'application/json' }
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== 'success' ||
        !Array.isArray(payload.classes) || !Array.isArray(payload.periods) ||
        !Array.isArray(payload.attendance)) {
      throw new Error(payload.message || `Could not prepare offline class data (HTTP ${response.status}).`);
    }
    await storeRecord(SEED_STORE, {
      cacheKey: seedCacheKey(),
      data: payload,
      savedAt: Date.now()
    });
    return payload;
  }

  async function getSeedData() {
    const record = await readRecord(SEED_STORE, seedCacheKey());
    return record ? record.data : null;
  }

  async function initializeSeedData() {
    if (navigator.onLine) {
      try {
        return await hydrateSeedData();
      } catch (error) {
        console.warn('Could not refresh offline attendance data:', error);
      }
    }
    return getSeedData();
  }

  async function getSeededStudents(program, part, date, period) {
    const seed = await getSeedData();
    if (!seed) return null;
    const classData = seed.classes.find(item =>
      item.program === program && item.part === part
    );
    if (!classData) return [];
    const savedStatuses = new Map();
    for (const record of seed.attendance) {
      if (record.date === date && String(record.period) === String(period)) {
        savedStatuses.set(String(record.student_id), record.status);
      }
    }
    return classData.students.map(student => ({
      ...student,
      saved_status: savedStatuses.get(String(student.id)) || ''
    }));
  }

  async function saveAttendanceLocally(attendance) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(SEED_STORE, 'readwrite');
      const store = transaction.objectStore(SEED_STORE);
      const request = store.get(seedCacheKey());
      request.onsuccess = () => {
        const seedRecord = request.result;
        if (!seedRecord) {
          transaction.abort();
          return;
        }
        const records = seedRecord.data.attendance;
        const studentId = String(attendance.student_id);
        const match = records.find(record =>
          String(record.student_id) === studentId &&
          record.date === attendance.date &&
          String(record.period) === String(attendance.period)
        );
        const updatedRecord = {
          student_id: attendance.student_id,
          roll_no: attendance.roll,
          date: attendance.date,
          period: Number(attendance.period),
          status: attendance.status,
          client_timestamp: attendance.client_timestamp
        };
        if (match) {
          Object.assign(match, updatedRecord);
        } else {
          records.push(updatedRecord);
        }
        store.put(seedRecord);
      };
      request.onerror = () => reject(request.error || new Error('Could not update saved attendance.'));
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error || new Error('Could not update saved attendance.'));
      transaction.onabort = () => reject(transaction.error || new Error('Attendance cache update was aborted.'));
    });
  }

  async function deriveCredentialVerifier(password, salt) {
    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(password),
      'PBKDF2',
      false,
      ['deriveBits']
    );
    const bits = await crypto.subtle.deriveBits({
      name: 'PBKDF2',
      salt,
      iterations: 310000,
      hash: 'SHA-256'
    }, key, 256);
    return Array.from(new Uint8Array(bits), byte => byte.toString(16).padStart(2, '0')).join('');
  }

  async function saveOfflineProfile(role, username, password) {
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const verifier = await deriveCredentialVerifier(password, salt);
    const profileKey = `offline-profile:${role}:${username}`;
    const authenticatedAt = Date.now();
    await storeRecord(PROFILE_STORE, {
      profileKey,
      role,
      username,
      salt: Array.from(salt),
      verifier,
      session: { role, username, offlineViewOnly: true, authenticatedAt },
      expiresAt: authenticatedAt + OFFLINE_PROFILE_MAX_AGE
    });
  }

  async function verifyOfflineProfile(role, username, password) {
    const profileKey = `offline-profile:${role}:${username}`;
    const profile = await readRecord(PROFILE_STORE, profileKey);
    if (!profile || profile.role !== role || profile.username !== username ||
        profile.session?.role !== role || profile.session?.username !== username ||
        profile.session?.offlineViewOnly !== true ||
        profile.expiresAt <= Date.now()) {
      return false;
    }
    const actual = await deriveCredentialVerifier(password, new Uint8Array(profile.salt));
    return actual === profile.verifier;
  }

  async function authorizeOfflineSession(role, username, password) {
    if (!await verifyOfflineProfile(role, username, password)) {
      return false;
    }
    if (!['admin', 'teacher', 'developer'].includes(role)) {
      throw new Error('Unsupported offline account role.');
    }
    const profile = await readRecord(PROFILE_STORE, `offline-profile:${role}:${username}`);
    if (!profile || profile.role !== role || profile.username !== username ||
        profile.expiresAt <= Date.now()) {
      throw new Error('Offline sign-in data is missing or expired.');
    }
    await storeRecord(OFFLINE_SESSION_STORE, {
      sessionKey: 'active',
      role,
      username,
      expiresAt: profile.expiresAt
    });
    return true;
  }

  async function enqueue(url, body, contentType, tag, operationId) {
    if (sessionStorage.getItem('offline-view-only') === 'true' && tag !== 'pending_attendance') {
      throw new Error('Offline sign-in only allows attendance to be queued. Connect and sign in online before changing other records.');
    }
    const actor = document.body.dataset.offlineActor;
    if (!actor) {
      throw new Error('Offline sync identity is not configured for this page.');
    }
    const path = allowedQueueUrl(url);
    if (!path) {
      throw new Error('This action cannot be queued for offline synchronization.');
    }

    const database = await openDatabase();
    const storeName = tag === 'pending_attendance' ? ATTENDANCE_STORE : STORE_NAME;
    const entry = {
      url: path,
      method: 'POST',
      body,
      contentType,
      actor,
      operationId,
      tag,
      createdAt: new Date().toISOString()
    };
    const id = await new Promise((resolve, reject) => {
      const transaction = database.transaction(storeName, 'readwrite');
      const store = transaction.objectStore(storeName);
      let savedId;
      if (tag === 'pending_attendance') {
        let submitted;
        try {
          submitted = JSON.parse(body);
        } catch (error) {
          transaction.abort();
          reject(new Error('Offline attendance must be valid JSON.'));
          return;
        }
        const studentKey = submitted.student_id !== undefined && submitted.student_id !== null
          ? `id:${String(submitted.student_id)}`
          : submitted.roll ? `roll:${String(submitted.roll)}` : '';
        if (!studentKey || !submitted.date || submitted.period === undefined || submitted.period === null) {
          transaction.abort();
          reject(new Error('Offline attendance is missing its student, date, or period.'));
          return;
        }
        const request = store.getAll();
        request.onsuccess = () => {
          const matches = request.result.filter(operation => {
            if (operation.url !== path || operation.method !== 'POST' ||
                operation.actor !== actor || operation.tag !== 'pending_attendance') return false;
            try {
              const queued = JSON.parse(operation.body);
              const queuedStudentKey = queued.student_id !== undefined && queued.student_id !== null
                ? `id:${String(queued.student_id)}`
                : queued.roll ? `roll:${String(queued.roll)}` : '';
              return queuedStudentKey === studentKey &&
                String(queued.date) === String(submitted.date) &&
                String(queued.period) === String(submitted.period);
            } catch (error) {
              return false;
            }
          }).sort((left, right) =>
            String(right.createdAt || '').localeCompare(String(left.createdAt || ''))
          );

          if (matches.length) {
            savedId = matches[0].id;
            store.put({ ...entry, id: savedId });
            matches.slice(1).forEach(operation => store.delete(operation.id));
          } else {
            const addRequest = store.add(entry);
            addRequest.onsuccess = () => {
              savedId = addRequest.result;
            };
            addRequest.onerror = () => transaction.abort();
          }
        };
        request.onerror = () => transaction.abort();
      } else {
        const request = store.add(entry);
        request.onsuccess = () => {
          savedId = request.result;
        };
        request.onerror = () => transaction.abort();
      }
      transaction.oncomplete = () => resolve(savedId);
      transaction.onerror = () => reject(transaction.error || new Error('Could not save the offline change.'));
      transaction.onabort = () => reject(transaction.error || new Error('Offline change save was aborted.'));
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
    const offlineViewOnly = sessionStorage.getItem('offline-view-only') === 'true';
    if (offlineViewOnly && tag !== 'pending_attendance') {
      throw new Error('Offline sign-in only allows attendance to be queued. Connect and sign in online before changing other records.');
    }
    const actor = document.body.dataset.offlineActor;
    if (!actor) {
      throw new Error('Offline sync identity is not configured for this page.');
    }
    const path = allowedQueueUrl(url);
    if (!path) {
      throw new Error('This action cannot be sent or queued for offline synchronization.');
    }
    const operationId = createOperationId();
    if (offlineViewOnly) {
      return { queued: true, id: await enqueue(path, body, contentType, tag, operationId) };
    }
    if (!navigator.onLine) {
      return { queued: true, id: await enqueue(path, body, contentType, tag, operationId) };
    }

    try {
      const response = await fetch(path, {
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
        return { queued: true, id: await enqueue(path, body, contentType, tag, operationId) };
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
      if (form.hasAttribute('data-no-offline-queue')) return;

      const endpointPath = allowedQueueUrl(form.action || location.href);
      if (!endpointPath) {
        return;
      }

      event.preventDefault();
      const submitter = event.submitter;
      const button = submitter instanceof HTMLButtonElement ? submitter : form.querySelector('button[type="submit"], button:not([type])');
      if (button) button.disabled = true;

      try {
        const formData = new FormData(form);
        if (submitter?.name) {
          formData.append(submitter.name, submitter.value);
        }
        const body = new URLSearchParams(formData);
        const result = await sendOrQueue(endpointPath, body.toString(), 'application/x-www-form-urlencoded;charset=UTF-8', actionTag(formData, new URL(endpointPath, location.origin).pathname));
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
    requestSync,
    saveSnapshot,
    getSnapshot,
    hydrateSeedData,
    getSeedData,
    initializeSeedData,
    getSeededStudents,
    saveAttendanceLocally,
    saveOfflineProfile,
    authorizeOfflineSession
  };

  if (sessionStorage.getItem('offline-view-only') === 'true') {
    const notice = document.createElement('div');
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');
    notice.textContent = document.body.dataset.offlineActor?.startsWith('teacher:')
      ? 'Offline session: attendance is saved on this device; other changes require online sign-in.'
      : 'Offline viewing mode: changes cannot be saved until you sign in online.';
    notice.style.cssText = 'position:sticky;top:0;z-index:10002;padding:10px 14px;margin-bottom:12px;border-radius:6px;background:#cff4fc;color:#055160;font-weight:600;';
    document.body.prepend(notice);
  }

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
