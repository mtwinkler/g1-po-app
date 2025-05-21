// order-processing-app-frontend/public/sw.js
self.addEventListener('push', function(event) {
  console.log('[Service Worker] Push Received.');
  let notificationData = {};
  try {
    notificationData = event.data.json().notification;
  } catch (e) {
    notificationData = {
      title: 'G1 PO App',
      body: event.data ? event.data.text() : 'You have a new notification.',
      icon: '/logo192.png', // Ensure this icon exists in your public folder
      data: { url: '/' } 
    };
  }

  const title = notificationData.title || 'G1 PO App Notification';
  const options = {
    body: notificationData.body || 'You have a new message.',
    icon: notificationData.icon || '/logo192.png',
    badge: notificationData.badge || '/logo72.png', // Optional: ensure this exists
    data: notificationData.data || { url: '/' }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
  console.log('[Service Worker] Notification click Received.');
  event.notification.close();
  if (event.notification.data && event.notification.data.url) {
    event.waitUntil(clients.openWindow(event.notification.data.url));
  } else {
    event.waitUntil(clients.openWindow('/'));
  }
});

self.addEventListener('install', event => console.log('[Service Worker] Install'));
self.addEventListener('activate', event => console.log('[Service Worker] Activate'));
