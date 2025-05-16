// App.jsx

import React from 'react';
import './App.css';
import { Routes, Route, Link, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';

// --- Import Components ---
import Dashboard from './components/Dashboard';
import SupplierList from './components/SupplierList';
import SupplierForm from './components/SupplierForm';
import EditSupplierForm from './components/EditSupplierForm';
// ProductMappingList, ProductMappingForm, EditProductMappingForm are removed as per request
import OrderDetail from './components/OrderDetail';
import Login from './components/Login';
import ProtectedRoute from './components/ProtectedRoute';

// Main App content component
function AppContent() {
  const { currentUser, logout } = useAuth();

  return (
    <div className="App">
      <nav className="main-navigation">
        {currentUser && (
          <>
            {/* Link to the main dashboard view (orders) */}
            <Link to="/dashboard">Orders</Link> |{' '}
            <Link to="/suppliers">Suppliers</Link> |{' '}
            {/* Changed "Products" to "Daily Sales" and updated the link */}
            <Link to="/dashboard/sales">Daily Sales</Link>
            <button
              onClick={async () => {
                try {
                  await logout();
                  // Navigate to login or rely on ProtectedRoute to redirect
                } catch (e) {
                  console.error("Logout failed", e);
                }
              }}
              style={{
                marginLeft: '20px',
                background: 'none',
                border: 'none',
                color: 'var(--text-nav-link)', // Ensure this CSS variable is defined
                cursor: 'pointer',
                textDecoration: 'underline',
                padding: '0',
                fontSize: 'inherit'
              }}
            >
              Logout
            </button>
          </>
        )}
        {!currentUser && (
          <Link to="/login" style={{fontWeight: 'bold'}}>Login</Link>
        )}
      </nav>

      <div id="page-content" style={{paddingTop: '1rem'}}>
        <Routes>
          {/* Public Login Route */}
          <Route path="/login" element={<Login />} />

          {/* Protected Routes */}
          {/* Route for the main dashboard (defaults to orders view) */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Dashboard initialView="orders" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard initialView="orders" />
              </ProtectedRoute>
            }
          />
          {/* New route for the Daily Sales view of the Dashboard */}
          <Route
            path="/dashboard/sales"
            element={
              <ProtectedRoute>
                <Dashboard initialView="dailySales" />
              </ProtectedRoute>
            }
          />

          {/* Supplier Routes */}
          <Route path="/suppliers" element={<ProtectedRoute><SupplierList /></ProtectedRoute>} />
          <Route path="/suppliers/add" element={<ProtectedRoute><SupplierForm /></ProtectedRoute>} />
          <Route path="/suppliers/edit/:supplierId" element={<ProtectedRoute><EditSupplierForm /></ProtectedRoute>} />

          {/* Product Mapping Routes - REMOVED as per request */}
          {/*
          <Route path="/products" element={<ProtectedRoute><ProductMappingList /></ProtectedRoute>} />
          <Route path="/products/add" element={<ProtectedRoute><ProductMappingForm /></ProtectedRoute>} />
          <Route path="/products/edit/:productId" element={<ProtectedRoute><EditProductMappingForm /></ProtectedRoute>} />
          */}

          {/* Order Detail Route */}
          <Route path="/orders/:orderId" element={<ProtectedRoute><OrderDetail /></ProtectedRoute>} />

          {/* Catch-all Route for 404 Not Found */}
          <Route
            path="*"
            element={
              currentUser ? (
                <div>Page not found. Go to <Link to="/dashboard">Dashboard</Link>.</div>
              ) : (
                <Navigate to="/login" />
              )
            }
          />
        </Routes>
      </div>
    </div>
  );
}

// Wrapper App component that includes AuthProvider
function App() {
  // console.log("VITE_API_BASE_URL from deployed app:", import.meta.env.VITE_API_BASE_URL);
  // BrowserRouter should be in main.jsx/index.jsx
  return (
    <AuthProvider>
      <AppContent />
      {/* Ensure BrowserRouter is wrapping this App component in your main.jsx or index.jsx file */}
    </AuthProvider>
  );
}

export default App;
