import React from 'react';
import './App.css'; // Assuming your global styles and utility card styles are here or imported by it
import { Routes, Route, Link, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';

// --- Import Core Page/Component Views ---
import Dashboard from './components/Dashboard';
import OrderDetail from './components/OrderDetail';
import Login from './components/Login';
import ProtectedRoute from './components/ProtectedRoute';

// --- Import Utilities Section Components ---
// Ensure these paths are correct based on your project structure
import StandaloneUpsLabel from './components/StandaloneUpsLabel';
import UtilitiesLandingPage from './components/UtilitiesLandingPage'; // You need to create this file
import SupplierList from './components/SupplierList'; // Main page for Supplier Management
import HpeDescriptionList from './components/HpeDescriptionList'; // NEWimport HpeDescriptionForm from './components/HpeDescriptionForm';
import HpeDescriptionForm from './components/HpeDescriptionForm';
import EditHpeDescriptionForm from './components/EditHpeDescriptionForm';
import QuickbooksSync from './components/QuickbooksSync'; // Page for QuickBooks Sync functionality

// If you have separate pages for adding/editing suppliers or products,
// you would import them here and add their routes as well.
// For example:
// import SupplierForm from './components/SupplierForm';
// import EditSupplierForm from './components/EditSupplierForm';
// import ProductMappingForm from './components/ProductMappingForm';
// import EditProductMappingForm from './components/EditProductMappingForm';


// Main App content component
function AppContent() {
  const { currentUser, logout } = useAuth(); // logout function is available from context

  return (
    <div className="App">
      <nav className="main-navigation">
        {currentUser && (
          <>
            <Link to="/dashboard">Orders</Link> |{' '}
            <Link to="/dashboard/sales">Daily Sales</Link> |{' '}
            <Link to="/utilities">Utilities</Link>
            {/* 
            // Example Logout Button - uncomment and style if needed
            <button
              onClick={async () => {
                try {
                  await logout();
                  // Navigation to /login will be handled by ProtectedRoute
                } catch (e) {
                  console.error("Logout failed", e);
                }
              }}
              style={{ 
                marginLeft: '20px', 
                background: 'none', 
                border: 'none', 
                color: 'var(--text-nav-link)', // Ensure CSS var is defined
                cursor: 'pointer', 
                textDecoration: 'underline', 
                padding: '0', 
                fontSize: 'inherit'
              }}
            >
              Logout
            </button>
            */}
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
          <Route 
            path="/admin/suppliers" 
            element={ 
              <ProtectedRoute>
                <SupplierList />
              </ProtectedRoute>
            } 
          />
          {/* 
            If you have separate pages for adding/editing suppliers, add routes like:
            <Route path="/admin/suppliers/add" element={<ProtectedRoute><SupplierForm /></ProtectedRoute>} />
            <Route path="/admin/suppliers/edit/:supplierId" element={<ProtectedRoute><EditSupplierForm /></ProtectedRoute>} />
          */}
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
              path="/admin/hpe-descriptions/edit/:optionPnParam" // Ensure param name matches useParams
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
      {/* 
        If you use a pdfIcon for preloading, ensure the path is correct (e.g., from public folder or imported)
        <img src="/pdf-icon.png" alt="preload pdf icon" style={{ width: 1, height: 1, opacity: 0, position: 'absolute', left: 0, top: 0, pointerEvents: 'none' }} /> 
      */}
    </div>
  );
}

// Wrapper App component that includes AuthProvider
function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;