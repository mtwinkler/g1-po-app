// App.jsx
import React, { useEffect } from 'react';

import './App.css'; 
import { Routes, Route, Link, Navigate } from 'react-router-dom'; // Removed BrowserRouter as Router
import { AuthProvider, useAuth } from './contexts/AuthContext';

// --- Import Core Page/Component Views ---
import Dashboard from './components/Dashboard';
import OrderDetail from './components/OrderDetail';
import SendReceiptForm from './components/SendReceiptForm'; 
import SendWireTransferInvoiceForm from './components/SendWireTransferInvoiceForm'; // <--- ENSURE THIS LINE IS PRESENT AND CORRECT
import Login from './components/Login';
import CustomsInfoList from './components/CustomsInfoList'; // Adjust path as needed
import CustomsInfoForm from './components/CustomsInfoForm';   // Adjust path as needed
import ProtectedRoute from './components/ProtectedRoute';

// --- Import Utilities Section Components ---
import StandaloneUpsLabel from './components/StandaloneUpsLabel';
import UtilitiesLandingPage from './components/UtilitiesLandingPage'; 
import SupplierList from './components/SupplierList'; 
import HpeDescriptionList from './components/HpeDescriptionList'; 
import HpeDescriptionForm from './components/HpeDescriptionForm';
import EditHpeDescriptionForm from './components/EditHpeDescriptionForm';
import QuickbooksSync from './components/QuickbooksSync'; 
import DeleteOrderUtil from './components/DeleteOrderUtil';

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
          
          {/* --- THIS ROUTE IS CORRECTLY DEFINED AS PER PREVIOUS STEP --- */}
          <Route 
            path="/orders/:orderId/send-receipt-form" 
            element={
                <ProtectedRoute>
                    <SendReceiptForm />
                </ProtectedRoute>
            } 
          />
          {/* --- END OF SEND RECEIPT FORM ROUTE --- */}

      {/* --- NEW ROUTE FOR SEND WIRE TRANSFER INVOICE FORM --- */}
      <Route 
        path="/orders/:orderId/send-wire-invoice-form" 
        element={
            <ProtectedRoute>
                <SendWireTransferInvoiceForm />
            </ProtectedRoute>
        } 
      />
      {/* --- END OF NEW ROUTE --- */}

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
          <Route 
            path="/utils/suppliers" 
            element={ 
              <ProtectedRoute>
                <SupplierList />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/utils/suppliers/add"
            element={
              <ProtectedRoute>
                <SupplierForm />
              </ProtectedRoute>
            } 
          />
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

          <Route path="/utils/delete-order" element={<ProtectedRoute><DeleteOrderUtil /></ProtectedRoute>} />

          {/* --- Customs Product Information CRUD --- */}
          <Route path="/admin/customs-info" element={
              <ProtectedRoute>
                  <CustomsInfoList />
              </ProtectedRoute>
          } />
          <Route path="/admin/customs-info/add" element={
              <ProtectedRoute>
                  <CustomsInfoForm />
              </ProtectedRoute>
          } />
          <Route path="/admin/customs-info/edit/:itemId" element={ 
              <ProtectedRoute>
                  <CustomsInfoForm />
              </ProtectedRoute>
          } />

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
    <AuthProvider>
        <AppContent />
    </AuthProvider>
  );
}

export default App;