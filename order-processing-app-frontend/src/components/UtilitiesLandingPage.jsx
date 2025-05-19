// src/components/UtilitiesLandingPage.jsx (or src/pages/UtilitiesLandingPage.jsx)
import React from 'react';
import { Link } from 'react-router-dom';
// If you have a specific CSS file for this page:
// import './UtilitiesLandingPage.css'; 
// Otherwise, styles from App.css (.utilities-container, .utilities-grid, .utility-card) will apply

function UtilitiesLandingPage() {
  return (
    <div className="utilities-container">
      <h1>Application Utilities</h1>
      <div className="utilities-grid">
        
        <Link to="/utils/standalone-label-generator" className="utility-card">
          <h2>Standalone UPS Label Generator</h2>
          <p>Quickly generate ad-hoc UPS shipping labels for miscellaneous shipments.</p>
        </Link>

        {/* Assuming QuickbooksSync.jsx now has a default export, even if placeholder */}
        <Link to="/utils/quickbooks-sync" className="utility-card">
          <h2>QuickBooks Integration</h2>
          <p>Sync Purchase Orders and Sales Orders to QuickBooks Desktop.</p>
        </Link>

        {/* --- UPDATED: Supplier Management is now an active link --- */}
        <Link to="/admin/suppliers" className="utility-card">
          <h2>Supplier Management</h2>
          <p>Add, view, edit, and manage supplier information and contacts.</p>
        </Link>

        {/* --- UPDATED: Product Management is now an active link --- */}
        <Link to="/admin/hpe-descriptions" className="utility-card">
          <h2>Custom Product Descriptions</h2>
          <p>Manage PO descriptions for HPE Option PNs.</p>
        </Link>

        {/* Placeholder for future utilities, e.g., FedEx Standalone Label Generator */}
        {/*
        <div className="utility-card" style={{opacity: 0.5, cursor: "not-allowed"}}>
            <h2>Standalone FedEx Label Generator</h2>
            <p>Generate ad-hoc FedEx shipping labels. (Coming Soon)</p>
        </div>
        */}

      </div>
    </div>
  );
}

export default UtilitiesLandingPage;