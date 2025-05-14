// src/contexts/AuthContext.js
import React, { useContext, useState, useEffect } from 'react';
import { auth } from '../firebase'; // Ensure this path to your firebase.js is correct
import { onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth';

const AuthContext = React.createContext();

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true); // <<< Must be initially true

  function signInWithGoogle() {
    const provider = new GoogleAuthProvider();
    return signInWithPopup(auth, provider);
  }

  function logout() {
    return signOut(auth);
  }

  useEffect(() => {
    console.log('AuthContext: useEffect running, setting up onAuthStateChanged.'); // Debug log
    const unsubscribe = onAuthStateChanged(auth, user => {
      console.log('AuthContext: onAuthStateChanged fired! User:', user); // Debug log
      setCurrentUser(user);
      setLoading(false); // <<< CRITICAL: Set loading to false here
      console.log('AuthContext: setLoading(false) called.'); // Debug log
    });

    return () => {
      console.log('AuthContext: Unsubscribing from onAuthStateChanged.'); // Debug log
      unsubscribe(); // Cleanup subscription on unmount
    };
  }, []); // Empty dependency array means this runs once on mount and cleans up on unmount

  const value = {
    currentUser,
    signInWithGoogle,
    logout,
    loading // Expose loading state
  };

  // Log before returning the provider
  console.log('AuthContext: AuthProvider rendering. Loading state:', loading, 'CurrentUser:', currentUser);

  return (
    <AuthContext.Provider value={value}>
      {!loading && children} {/* <<< CRITICAL: Only render children when not loading */}
    </AuthContext.Provider>
  );
}