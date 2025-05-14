console.log("VITE_API_BASE_URL from deployed app:", import.meta.env.VITE_API_BASE_URL);


import { useState, useEffect } from 'react'; // Keep existing imports if needed elsewhere in App (less likely after refactoring)
import './App.css'; // Keep default styling if you want

// --- Import Routes, Route, and Link from react-router-dom ---
import { Routes, Route, Link } from 'react-router-dom';

// --- Import all the components you have created ---
import Dashboard from './components/Dashboard'; // Import the new Dashboard component
import SupplierList from './components/SupplierList';
import SupplierForm from './components/SupplierForm';
import EditSupplierForm from './components/EditSupplierForm';
import ProductMappingList from './components/ProductMappingList';
import ProductMappingForm from './components/ProductMappingForm';
import EditProductMappingForm from './components/EditProductMappingForm';
import OrderDetail from './components/OrderDetail'; // Import OrderDetail component


function App() {
  // --- Remove the old dashboard state and useEffect from here ---
  // They are now in the Dashboard.jsx component


  // --- Main App Component Structure ---
  return (
    <div className="App">
      <nav className="main-navigation">
        {/* --- Basic Navigation Links --- */}
        {/* Use Link components for client-side navigation */}
        <Link to="/">Dashboard</Link> |{' '}
        <Link to="/suppliers">Suppliers</Link> |{' '}
        <Link to="/products">Products</Link>
        {/* Add other top-level links here */}
      </nav>

      {/* --- Define Routes --- */}
      {/* Routes component wraps individual Route components */}
      <Routes>
        {/* --- Route for the Dashboard --- */}
        {/* Renders the Dashboard component when the path is exactly "/" */}
        <Route path="/" element={<Dashboard />} exact />


        {/* --- Routes for Supplier Management --- */}
        {/* Renders SupplierList when path is exactly "/suppliers" */}
        <Route path="/suppliers" element={<SupplierList />} />
        {/* Renders SupplierForm for adding new suppliers */}
        <Route path="/suppliers/add" element={<SupplierForm />} />
        {/* Renders EditSupplierForm for editing a specific supplier */}
        {/* :supplierId is a URL parameter that react-router-dom captures and passes to the component via useParams */}
        <Route path="/suppliers/edit/:supplierId" element={<EditSupplierForm />} />


        {/* --- Routes for Product Mapping Management --- */}
        {/* Renders ProductMappingList when path is exactly "/products" */}
        <Route path="/products" element={<ProductMappingList />} />
        {/* Renders ProductMappingForm for adding new mappings */}
        <Route path="/products/add" element={<ProductMappingForm />} />
        {/* Renders EditProductMappingForm for editing a specific mapping */}
        {/* :productId is a URL parameter captured by react-router-dom */}
        <Route path="/products/edit/:productId" element={<EditProductMappingForm />} />


        {/* --- Route for viewing Order Details --- */}
        {/* Renders OrderDetail component when path matches "/orders/" followed by any ID */}
        {/* :orderId is a URL parameter captured by react-router-dom */}
        <Route path="/orders/:orderId" element={<OrderDetail />} />


        {/* --- Optional: Add a Catch-all Route for 404 Not Found --- */}
        {/* This route will match any path that hasn't been matched by the routes above */}
        {/* You would create a simple NotFound component (e.g., showing "Page not found") */}
        {/* <Route path="*" element={<div>Page not found</div>} /> */}


      </Routes>

      {/* Content below Routes will appear on all pages */}
      {/* Optional: Add a footer or other global elements here */}
    </div>
  );
}

// --- Export the App component ---
export default App;