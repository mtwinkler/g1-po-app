// src/pages/UtilitiesLandingPage.jsx
import React from 'react';
import { Link } from 'react-router-dom';
// If you create a specific CSS file for this page:
// import './UtilitiesLandingPage.css'; 

function UtilitiesLandingPage() {
  return (
    <div className="utilities-container"> {/* Use class from App.css */}
      <h1>Application Utilities</h1>
      <div className="utilities-grid"> {/* Use class from App.css */}
        
        <Link to="/utils/standalone-label-generator" className="utility-card">
          <h2>Standalone UPS Label Generator</h2>
          <p>Quickly generate ad-hoc UPS shipping labels for miscellaneous shipments.</p>
        </Link>

        {/* Placeholder for QuickBooks - uncomment and update 'to' when page is ready */}
        {/*
        <Link to="/utils/quickbooks-sync" className="utility-card">
          <h2>QuickBooks Integration</h2>
          <p>Sync Purchase Orders and Sales Orders to QuickBooks Desktop.</p>
        </Link>
        */}
        <div className="utility-card" style={{opacity: 0.5, cursor: "not-allowed"}}> {/* Example of a disabled-looking card */}
            <h2>QuickBooks Integration</h2>
            <p>Sync Purchase Orders and Sales Orders to QuickBooks. (Coming Soon)</p>
        </div>


        {/* Placeholder for Supplier Management - uncomment and update 'to' when page is ready */}
        {/*
        <Link to="/admin/suppliers" className="utility-card">
          <h2>Supplier Management</h2>
          <p>Add, view, edit, and manage supplier information and contacts.</p>
        </Link>
        */}
         <div className="utility-card" style={{opacity: 0.5, cursor: "not-allowed"}}>
            <h2>Supplier Management</h2>
            <p>Add, view, edit, and manage supplier information. (Coming Soon - API exists)</p>
        </div>


        {/* Placeholder for Product Management - uncomment and update 'to' when page is ready */}
        {/*
        <Link to="/admin/products" className="utility-card">
          <h2>Product Management</h2>
          <p>Manage internal product SKU mappings and default descriptions.</p>
        </Link>
        */}
        <div className="utility-card" style={{opacity: 0.5, cursor: "not-allowed"}}>
            <h2>Product Management</h2>
            <p>Manage internal product SKU mappings. (Coming Soon - API exists)</p>
        </div>

        {/* You can add more utility cards here as you develop them */}

      </div>
    </div>
  );
}

export default UtilitiesLandingPage;