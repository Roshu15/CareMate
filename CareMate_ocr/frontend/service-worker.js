const CACHE_NAME = 'caremate-shell-v3';
const APP_SHELL = [
  '/',
  '/static/app.css?v=20261104-mobile-layout4',
  '/static/app.js?v=20261104-local-push1',
  '/static/manifest.webmanifest',
  '/static/icons/caremate-192.png',
  '/static/icons/caremate-512.png',
  '/static/icons/caremate-maskable-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('caremate-shell-') && key !== CACHE_NAME).map(key => caches.delete(key))
  )));
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(response => {
      if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put('/', response.clone()));
      return response;
    }).catch(async () => (await caches.match('/')) || Response.error()));
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
      if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone()));
      return response;
    })));
  }
});

self.addEventListener('push', event => {
  let message = { title: 'CareMate alert', body: 'Open CareMate to review a new care alert.' };
  try { if (event.data) message = { ...message, ...event.data.json() }; } catch {}
  event.waitUntil(self.registration.showNotification(message.title, {
    body: message.body,
    icon: '/static/icons/caremate-192.png',
    badge: '/static/icons/caremate-192.png',
    tag: `caremate-push-${message.id || Date.now()}`,
    renotify: true,
    silent: false,
    data: { url: '/' }
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients) if ('focus' in client) return client.focus();
    return self.clients.openWindow(event.notification.data?.url || '/');
  })());
});
