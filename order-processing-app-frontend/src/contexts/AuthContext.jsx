import React, { useContext, useState, useEffect, useCallback } from 'react'; // Added useCallback
import { auth } from '../firebase';
import { onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth';

const AuthContext = React.createContext();

export function useAuth() {
  return useContext(AuthContext);
}

// --- Define API Base URL ---
// It's good practice to get this from environment variables, especially for different environments
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080/api';
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

  // --- API Service Logic ---
  const getAuthToken = useCallback(async () => {
    if (auth.currentUser) {
      try {
        return await auth.currentUser.getIdToken(true); // true forces refresh
      } catch (error) {
        console.error("Error getting ID token:", error);
        // Handle token refresh errors, e.g., by logging out the user
        if (error.code === 'auth/user-token-expired' || error.code === 'auth/user-disabled' || error.code === 'auth/user-not-found') {
            await logout(); // Attempt to log out the user if token is invalid
            throw new Error("User session expired or invalid. Please log in again.");
        }
        return null;
      }
    }
    return null;
  }, []); // auth.currentUser is not a stable dependency here, rely on its presence

  const apiService = {
    get: useCallback(async (endpoint, params = {}) => {
      const token = await getAuthToken();
      if (!token) throw new Error("User not authenticated or token unavailable.");

      const url = new URL(`${API_BASE_URL}${endpoint}`);
      Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
        throw { status: response.status, data: errorData, message: errorData.message || response.statusText };
      }
      return response.json();
    }, [getAuthToken]), // Dependency on getAuthToken

    post: useCallback(async (endpoint, data) => {
      const token = await getAuthToken();
      if (!token) throw new Error("User not authenticated or token unavailable.");

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
        throw { status: response.status, data: errorData, message: errorData.message || response.statusText };
      }
      // Handle cases where POST might return no content (204) or just status (201 without body)
      if (response.status === 204 || response.headers.get("content-length") === "0") {
        return { message: "Operation successful with no content.", status: response.status, tracking_number: null }; // Adjust if needed
      }
      return response.json();
    }, [getAuthToken]), // Dependency on getAuthToken

    // You can add put, delete methods similarly if needed
    // put: useCallback(async (endpoint, data) => { ... }, [getAuthToken]),
    // delete: useCallback(async (endpoint) => { ... }, [getAuthToken]),
  };
  // --- End API Service Logic ---


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
    apiService, // <<< Add apiService to the context value
  };

  console.log('AuthContext: AuthProvider rendering. Loading state:', loading, 'CurrentUser:', !!currentUser);

  return (
    <AuthContext.Provider value={value}>
      {!loading && children}
    </AuthContext.Provider>
  );
}
