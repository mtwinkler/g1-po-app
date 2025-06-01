// src/contexts/AuthContext.jsx

import React, { useContext, useState, useEffect, useCallback } from 'react';
import { auth } from '../firebase'; // Assuming firebase.js is in a sibling directory
import { onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth';

export const AuthContext = React.createContext(); // <<< MODIFIED: Added export

export function useAuth() {
  return useContext(AuthContext);
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
console.log("AuthContext: API_BASE_URL is set to:", API_BASE_URL);


export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);

  function signInWithGoogle() {
    const provider = new GoogleAuthProvider();
    return signInWithPopup(auth, provider);
  }

  function logout() {
    return signOut(auth);
  }

  const getAuthToken = useCallback(async () => {
    if (auth.currentUser) {
      try {
        return await auth.currentUser.getIdToken(true);
      } catch (error) {
        console.error("Error getting ID token:", error);
        if (error.code === 'auth/user-token-expired' || error.code === 'auth/user-disabled' || error.code === 'auth/user-not-found') {
            await logout(); // Consider navigating the user to login after this
            throw new Error("User session expired or invalid. Please log in again.");
        } else if (error.code === 'auth/quota-exceeded') { // Specific check for quota
            throw new Error("Authentication service quota exceeded. Please contact support or try again later.");
        }
        // For other errors, it might be better to throw an error than return null,
        // so apiService directly catches a more specific issue.
        // Or, ensure any path returning null leads to a clear user message.
        throw new Error("Failed to obtain authentication token due to an unexpected error."); // More generic for other caught errors
      }
    }
    // If auth.currentUser is null
    throw new Error("User not currently signed in."); // More specific than just "token unavailable"
  }, [logout]); // Assuming logout is stable or wrapped in useCallback if it comes from props

  const apiService = {
    get: useCallback(async (endpoint, queryParams = {}, options = {}) => {
      try {
        const token = await getAuthToken(); // This will now throw more specific errors
        // The 'if (!token)' check below becomes less critical if getAuthToken always throws on failure
        // but it's a good defensive check if getAuthToken could somehow still return null for some paths.
        // Given the revised getAuthToken, this specific error might not be reached if getAuthToken always throws.
        if (!token) throw new Error("User not authenticated or token unavailable (getAuthToken returned null)."); 
        
        const url = new URL(`${API_BASE_URL}${endpoint}`);
        Object.keys(queryParams).forEach(key => url.searchParams.append(key, queryParams[key]));
        const response = await fetch(url, {
          method: 'GET',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', }, ...options,
        });
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
          const errorToThrow = new Error(errorData.message || response.statusText);
          errorToThrow.status = response.status; errorToThrow.data = errorData; throw errorToThrow;
        }
        return response.json();
      } catch (error) {
          // Re-throw the error so the component calling apiService.get() can catch it.
          // This allows components to display specific messages based on the error type.
          console.error(`apiService.get error for endpoint ${endpoint}:`, error.message);
          throw error; 
      }
    }, [getAuthToken]),

    post: useCallback(async (endpoint, bodyData, options = {}) => {
      const token = await getAuthToken();
      if (!token) throw new Error("User not authenticated or token unavailable.");
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', },
        body: JSON.stringify(bodyData), ...options,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
        const errorToThrow = new Error(errorData.message || response.statusText);
        errorToThrow.status = response.status; errorToThrow.data = errorData; throw errorToThrow;
      }
      if (response.status === 204 || response.headers.get("content-length") === "0") {
        return { message: "Operation successful with no content.", status: response.status };
      }
      return response.json();
    }, [getAuthToken]),

    put: useCallback(async (endpoint, bodyData, options = {}) => {
        const token = await getAuthToken();
        if (!token) throw new Error("User not authenticated or token unavailable.");
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', },
            body: JSON.stringify(bodyData), ...options,
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
            const errorToThrow = new Error(errorData.message || response.statusText);
            errorToThrow.status = response.status; errorToThrow.data = errorData; throw errorToThrow;
        }
        if (response.status === 204 || response.headers.get("content-length") === "0") {
          return { message: "Update successful with no content.", status: response.status };
        }
        return response.json();
    }, [getAuthToken]),

    delete: useCallback(async (endpoint, options = {}) => {
        const token = await getAuthToken();
        if (!token) throw new Error("User not authenticated or token unavailable.");
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'DELETE', headers: { 'Authorization': `Bearer ${token}`, }, ...options,
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
            const errorToThrow = new Error(errorData.message || response.statusText);
            errorToThrow.status = response.status; errorToThrow.data = errorData; throw errorToThrow;
        }
        if (response.status === 204 || response.headers.get("content-length") === "0") {
          return { message: "Deletion successful.", status: response.status };
        }
        return response.json();
    }, [getAuthToken]),
  };

  useEffect(() => {
    console.log('AuthContext: useEffect running, setting up onAuthStateChanged.');
    const unsubscribe = onAuthStateChanged(auth, user => {
      console.log('AuthContext: onAuthStateChanged fired! User:', user);
      setCurrentUser(user);
      setLoading(false);
      console.log('AuthContext: setLoading(false) called.');
    });
    return () => {
      console.log('AuthContext: Unsubscribing from onAuthStateChanged.');
      unsubscribe();
    };
  }, []);

  const value = {
    currentUser,
    signInWithGoogle,
    logout,
    loading,
    apiService,
  };

  console.log('AuthContext: AuthProvider rendering. Loading state:', loading, 'CurrentUser:', !!currentUser);

  return (
    <AuthContext.Provider value={value}>
      {!loading && children}
    </AuthContext.Provider>
  );
}