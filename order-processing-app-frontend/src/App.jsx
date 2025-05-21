// App.jsx
import React, { useEffect } from 'react';

import './App.css'; 
import { Routes, Route, Link, Navigate } from 'react-router-dom'; // Removed BrowserRouter as Router
import { AuthProvider, useAuth } from './contexts/AuthContext';

// --- Import Core Page/Component Views ---
import Dashboard from './components/Dashboard';
import OrderDetail from './components/OrderDetail';
import Login from './components/Login';
import ProtectedRoute from './components/ProtectedRoute';

// --- Import Utilities Section Components ---
import StandaloneUpsLabel from './components/StandaloneUpsLabel';
import UtilitiesLandingPage from './components/UtilitiesLandingPage'; 
import SupplierList from './components/SupplierList'; 
import HpeDescriptionList from './components/HpeDescriptionList'; 
import HpeDescriptionForm from './components/HpeDescriptionForm';
import EditHpeDescriptionForm from './components/EditHpeDescriptionForm';
import QuickbooksSync from './components/QuickbooksSync'; 

// --- MODIFICATION: Uncomment and ensure correct paths for Supplier Forms ---
import SupplierForm from './components/SupplierForm';
import EditSupplierForm from './components/EditSupplierForm'; // Assuming you will create this file

// Main App content component
function AppContent() {
  const { currentUser, logout } = useAuth(); 

  return (
    <div className="App">
      <nav className="main-navigation">
        {currentUser && (
          <>
            <Link to="/dashboard">Orders</Link> |{' '}
            <Link to="/dashboard/sales">Daily Sales</Link> |{' '}
            <Link to="/utilities">Utilities</Link>
            <button
              onClick={async () => {
                try {
                  await logout();
                  // Navigation to /login will be handled by ProtectedRoute or similar logic
                } catch (e) {
                  console.error("Logout failed", e);
                }
              }}
              style={{ 
                marginLeft: '20px', 
                background: 'none', 
                border: 'none', 
                color: 'var(--text-nav-link, white)', // Added fallback color
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

          {/* Protected Routes - Core Application */}
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
          <Route
            path="/dashboard/sales"
            element={
              <ProtectedRoute>
                <Dashboard initialView="dailySales" />
              </ProtectedRoute>
            }
          />
          <Route 
            path="/orders/:orderId" 
            element={
              <ProtectedRoute>
                <OrderDetail />
              </ProtectedRoute>
            } 
          />
          
          {/* Utilities Section Routes */}
          <Route 
            path="/utilities" 
            element={
              <ProtectedRoute>
                <UtilitiesLandingPage />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/utils/standalone-label-generator" 
            element={
              <ProtectedRoute>
                <StandaloneUpsLabel />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/utils/quickbooks-sync" 
            element={
              <ProtectedRoute>
                <QuickbooksSync />
              </ProtectedRoute>
            } 
          />

          {/* --- MODIFICATION: Supplier CRUD Routes --- */}
          {/* Route to list all suppliers - path adjusted to match common pattern */}
          <Route 
            path="/utils/suppliers" 
            element={ 
              <ProtectedRoute>
                <SupplierList />
              </ProtectedRoute>
            } 
          />
          {/* Route to the form for adding a new supplier */}
          <Route 
            path="/utils/suppliers/add"
            element={
              <ProtectedRoute>
                <SupplierForm />
              </ProtectedRoute>
            } 
          />
          {/* Route to the form for editing an existing supplier */}
          <Route 
            path="/utils/suppliers/edit/:supplierId"
            element={
              <ProtectedRoute>
                <EditSupplierForm />
              </ProtectedRoute> 
            } 
          />
          {/* --- End Supplier CRUD Routes --- */}

          <Route 
            path="/admin/hpe-descriptions" 
            element={
              <ProtectedRoute>
                <HpeDescriptionList />
              </ProtectedRoute>
            } 
          />
          <Route 
              path="/admin/hpe-descriptions/add" 
              element={<ProtectedRoute><HpeDescriptionForm /></ProtectedRoute>} 
          />
          <Route 
              path="/admin/hpe-descriptions/edit/:optionPnParam" 
              element={<ProtectedRoute><EditHpeDescriptionForm /></ProtectedRoute>} 
          />

          {/* Catch-all Route for 404 Not Found */}
          <Route
            path="*"
            element={
              currentUser ? (
                <div style={{textAlign: 'center', marginTop: '2rem'}}>
                  <h2>Page Not Found</h2>
                  <p>The page you are looking for does not exist.</p>
                  <Link to="/dashboard" className="btn btn-primary btn-gradient btn-shadow-lift">Go to Dashboard</Link>
                </div>
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
        </Routes>
      </div>
    </div>
  );
}

function App() {
  return (
    // Router should wrap AppContent if AppContent uses routing features like Link, Routes, useAuth for nav
    // However, typically Router is at the very top level.
    // If AuthProvider doesn't depend on Router, this is fine.
    // If AuthProvider *does* use navigate or other router hooks, Router needs to be outside AuthProvider.
    // For now, assuming AuthProvider is independent or this structure is intended.
    <AuthProvider>
        <AppContent />
    </AuthProvider>
  );
}

export default App;
