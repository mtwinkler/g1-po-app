// App.jsx

import React from 'react'; // Import React if not already (though often implicit)
import './App.css';

// --- Import Routes, Route, Link from react-router-dom ---
// BrowserRouter (or Router alias) should wrap your App in main.jsx or index.jsx
import { Routes, Route, Link, Navigate } from 'react-router-dom';

// --- Import AuthProvider and useAuth hook ---
import { AuthProvider, useAuth } from './contexts/AuthContext'; // Create this file

// --- Import all the components you have created ---
import Dashboard from './components/Dashboard';
import SupplierList from './components/SupplierList';
import SupplierForm from './components/SupplierForm';
import EditSupplierForm from './components/EditSupplierForm';
import ProductMappingList from './components/ProductMappingList';
import ProductMappingForm from './components/ProductMappingForm';
import EditProductMappingForm from './components/EditProductMappingForm';
import OrderDetail from './components/OrderDetail';
import Login from './components/Login'; // Create this component
import ProtectedRoute from './components/ProtectedRoute'; // Create this component

// Main App content component
function AppContent() {
  const { currentUser, logout } = useAuth(); // Get auth state and logout function

  return (
    <div className="App">
      <nav className="main-navigation">
        {currentUser && (
          <>
            <Link to="/">Dashboard</Link> |{' '}
            <Link to="/suppliers">Suppliers</Link> |{' '}
            <Link to="/products">Products</Link>
            <button
              onClick={async () => {
                try {
                  await logout();
                  // Optional: navigate('/login') or rely on ProtectedRoute to redirect
                } catch (e) {
                  console.error("Logout failed", e);
                }
              }}
              style={{ marginLeft: '20px', background: 'none', border: 'none', color: 'var(--text-nav-link)', cursor: 'pointer', textDecoration: 'underline', padding: '0', fontSize: 'inherit' }}
            >
              Logout
            </button>
          </>
        )}
        {!currentUser && (
          <Link to="/login" style={{fontWeight: 'bold'}}>Login</Link> // Maybe style login link differently
        )}
      </nav>

      <div id="page-content" style={{paddingTop: '1rem'}}> {/* Add some padding if nav is fixed or takes space */}
        <Routes>
          {/* Public Login Route */}
          <Route path="/login" element={<Login />} />

          {/* Protected Routes */}
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} /> {/* Explicit dashboard route */}
          <Route path="/suppliers" element={<ProtectedRoute><SupplierList /></ProtectedRoute>} />
          <Route path="/suppliers/add" element={<ProtectedRoute><SupplierForm /></ProtectedRoute>} />
          <Route path="/suppliers/edit/:supplierId" element={<ProtectedRoute><EditSupplierForm /></ProtectedRoute>} />
          <Route path="/products" element={<ProtectedRoute><ProductMappingList /></ProtectedRoute>} />
          <Route path="/products/add" element={<ProtectedRoute><ProductMappingForm /></ProtectedRoute>} />
          <Route path="/products/edit/:productId" element={<ProtectedRoute><EditProductMappingForm /></ProtectedRoute>} />
          <Route path="/orders/:orderId" element={<ProtectedRoute><OrderDetail /></ProtectedRoute>} />

          {/* Optional: Add a Catch-all Route for 404 Not Found */}
          <Route path="*" element={
            currentUser ? <div>Page not found. Go to <Link to="/">Dashboard</Link>.</div> : <Navigate to="/login" />
          } />
        </Routes>
      </div>
    </div>
  );
}

// Wrapper App component that includes AuthProvider
function App() {
  console.log("VITE_API_BASE_URL from deployed app:", import.meta.env.VITE_API_BASE_URL);
  // BrowserRouter should be in main.jsx/index.jsx
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;