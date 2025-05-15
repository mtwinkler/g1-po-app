// src/firebase.js
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: "g1-po-app-77790.firebaseapp.com",
  projectId: "g1-po-app-77790",
  storageBucket: "g1-po-app-77790.firebasestorage.app",
  messagingSenderId: "567814517626",
  appId: "1:567814517626:web:27151d8a8ebaadb5a49cc3"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
export const auth = getAuth(app); // Export auth instance
export default app;