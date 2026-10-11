(function () {
  'use strict';

  const form = document.getElementById('login-form');
  const status = document.getElementById('login-status');
  const role = document.body.dataset.loginRole;
  const dashboardByRole = {
    admin: '/admin/dashboard',
    teacher: '/teacher/dashboard',
    developer: '/developer/dashboard'
  };

  if (!form || !status || !dashboardByRole[role] || !window.OfflineSync) {
    return;
  }

  function showStatus(message) {
    status.textContent = message;
    status.hidden = false;
  }

  async function continueOffline(username, password) {
    try {
      const valid = await window.OfflineSync.authorizeOfflineSession(role, username, password);
      if (!valid) {
        showStatus('No valid offline sign-in is available for these credentials. Connect and sign in online first. Offline access is view-only.');
        return;
      }
      sessionStorage.setItem('offline-view-only', 'true');
      window.location.assign(dashboardByRole[role]);
    } catch (error) {
      showStatus(error instanceof Error ? error.message : 'Could not validate offline sign-in.');
    }
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    const submitButton = form.querySelector('button[type="submit"]');
    const formData = new FormData(form);
    const username = String(formData.get('username') || '').trim();
    const password = String(formData.get('password') || '');
    if (submitButton) submitButton.disabled = true;
    status.hidden = true;

    try {
      if (!navigator.onLine) {
        await continueOffline(username, password);
        return;
      }
      sessionStorage.removeItem('offline-view-only');

      const response = await fetch(form.action || window.location.href, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
        body: new URLSearchParams({ username, password })
      });
      const result = await response.json();
      if (!response.ok || result.status !== 'success' ||
          result.role !== role || result.dashboard !== dashboardByRole[role]) {
        showStatus(result.message || 'The server rejected these credentials.');
        return;
      }

      try {
        await window.OfflineSync.saveOfflineProfile(role, username, password);
      } catch (error) {
        showStatus(`Online sign-in succeeded, but offline access could not be prepared: ${error.message}`);
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
      window.location.assign(result.dashboard);
    } catch (error) {
      if (!navigator.onLine || error instanceof TypeError) {
        await continueOffline(username, password);
      } else {
        showStatus(error instanceof Error ? error.message : 'Sign-in failed.');
      }
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
})();
