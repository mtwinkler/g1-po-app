import React, { useContext, useState, useEffect, useCallback } from 'react'; // Added useCallback
import { auth } from '../firebase';
import { onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth';

const AuthContext = React.createContext();

export function useAuth() {
  return useContext(AuthContext);
}

// --- Define API Base URL ---
// It's good practice to get this from environment variables, especially for different environments
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';
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
    get: useCallback(async (endpoint, queryParams = {}, options = {}) => { // Added options
      const token = await getAuthToken();
      if (!token) throw new Error("User not authenticated or token unavailable.");

      const url = new URL(`${API_BASE_URL}${endpoint}`);
      Object.keys(queryParams).forEach(key => url.searchParams.append(key, queryParams[key]));

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json', // Usually not needed for GET, but harmless
        },
        ...options, // Spread other options like signal here
      });
      // ... rest of error handling and response.json() ...
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
        // Use the error structure your components expect
        const errorToThrow = new Error(errorData.message || response.statusText);
        errorToThrow.status = response.status;
        errorToThrow.data = errorData;
        throw errorToThrow;
      }
      return response.json();
    }, [getAuthToken]), // API_BASE_URL is stable after init, getAuthToken is the main dep

    post: useCallback(async (endpoint, bodyData, options = {}) => { // Added options
      const token = await getAuthToken();
      if (!token) throw new Error("User not authenticated or token unavailable.");

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(bodyData),
        ...options, // Spread other options like signal here
      });
      // ... rest of error handling ...
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
        const errorToThrow = new Error(errorData.message || response.statusText);
        errorToThrow.status = response.status;
        errorToThrow.data = errorData;
        throw errorToThrow;
      }
      if (response.status === 204 || response.headers.get("content-length") === "0") {
        return { message: "Operation successful with no content.", status: response.status };
      }
      return response.json();
    }, [getAuthToken]),

    put: useCallback(async (endpoint, bodyData, options = {}) => { // Example PUT
        const token = await getAuthToken();
        if (!token) throw new Error("User not authenticated or token unavailable.");

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(bodyData),
            ...options,
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
            const errorToThrow = new Error(errorData.message || response.statusText);
            errorToThrow.status = response.status;
            errorToThrow.data = errorData;
            throw errorToThrow;
        }
        if (response.status === 204 || response.headers.get("content-length") === "0") {
          return { message: "Update successful with no content.", status: response.status };
        }
        return response.json();
    }, [getAuthToken]),

    delete: useCallback(async (endpoint, options = {}) => { // Example DELETE
        const token = await getAuthToken();
        if (!token) throw new Error("User not authenticated or token unavailable.");

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`,
            },
            ...options,
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: "Unknown error, response not JSON" }));
            const errorToThrow = new Error(errorData.message || response.statusText);
            errorToThrow.status = response.status;
            errorToThrow.data = errorData;
            throw errorToThrow;
        }
        // DELETE often returns 204 No Content on success
        if (response.status === 204 || response.headers.get("content-length") === "0") {
          return { message: "Deletion successful.", status: response.status };
        }
        return response.json(); // Or handle if it returns data
    }, [getAuthToken]),
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
