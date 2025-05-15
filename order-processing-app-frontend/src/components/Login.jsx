// src/components/Login.jsx
import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext'; // Adjust path if AuthContext is elsewhere
import { useNavigate, useLocation } from 'react-router-dom';
import signInButtonImg from '../assets/sign-in-button.png'; // <<<< IMPORT YOUR IMAGE
import './Login.css'; // Optional: Create this file for CSS if needed

function Login() {
  const { signInWithGoogle, currentUser, loading: authLoading } = useAuth(); // Get currentUser and authLoading
  const [error, setError] = useState('');
  const [isSigningIn, setIsSigningIn] = useState(false); // Local loading state for the sign-in process
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/dashboard"; // Default redirect to dashboard

  // If user is already logged in (and auth is not loading), redirect from login page
  useEffect(() => {
    if (!authLoading && currentUser) {
      navigate(from, { replace: true });
    }
  }, [currentUser, authLoading, navigate, from]);

  async function handleGoogleSignIn() {
    if (isSigningIn) return; // Prevent multiple clicks
    try {
      setError('');
      setIsSigningIn(true);
      await signInWithGoogle();
      // Successful sign-in will trigger onAuthStateChanged,
      // which updates currentUser, and the useEffect above will redirect.
      // Or ProtectedRoute will grant access.
      // navigate(from, { replace: true }); // Can be redundant if useEffect handles it
    } catch (e) {
      console.error("Failed to sign in with Google", e);
      setError('Failed to sign in. Please try again.');
    }
    setIsSigningIn(false);
  }

  // If Firebase Auth is still loading its initial state, show a generic loading message
  if (authLoading) {
    return <div style={{ textAlign: 'center', marginTop: '50px' }}>Loading session...</div>;
  }

  // If user is somehow already here and logged in (though useEffect should redirect)
  if (currentUser) {
    return <div style={{ textAlign: 'center', marginTop: '50px' }}>Already logged in. Redirecting...</div>;
  }

  return (
    <div className="login-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', padding: '20px' }}>
      <h2>G1 PO App Login</h2>
      <p style={{ marginBottom: '30px', fontSize: '0.7em', textAlign: 'center' }}>Please sign in with your Google account to continue.</p>
      
      {error && <p style={{ color: 'red', marginBottom: '15px' }}>{error}</p>}

      <button
        onClick={handleGoogleSignIn}
        disabled={isSigningIn}
        className="google-signin-custom-button" // For CSS styling
        aria-label="Sign In with Google"
      >
        <img
          src={signInButtonImg} // Use the imported image
          alt="Sign In with Google"
          style={{ display: 'block', width: '220px', height: 'auto' }} // Adjust width as needed
        />
      </button>

      {isSigningIn && <p style={{ marginTop: '15px' }}>Attempting to sign you in...</p>}
    </div>
  );
}

export default Login;