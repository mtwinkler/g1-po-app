// src/components/ProtectedRoute.jsx
import React from 'react';
import { useAuth } from '../contexts/AuthContext'; // Ensure path is correct
import { Navigate, useLocation } from 'react-router-dom';

function ProtectedRoute({ children }) {
  const { currentUser, loading } = useAuth();
  const location = useLocation();

  console.log('ProtectedRoute: Running. Context loading:', loading, 'Context currentUser:', currentUser); // Debug log

  if (loading) {
    console.log('ProtectedRoute: Auth context is loading. Showing loading message.'); // Debug log
    return <div style={{ textAlign: 'center', marginTop: '50px', fontSize: '1.2em' }}>Loading application...</div>;
  }

  if (!currentUser) {
    console.log('ProtectedRoute: No current user, redirecting to /login. Current location was:', location.pathname); // Debug log
    // Redirect them to the /login page, but save the current location they were
    // trying to go to so we can send them there after login.
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  console.log('ProtectedRoute: User is authenticated. Rendering children.'); // Debug log
  return children;
}

export default ProtectedRoute;