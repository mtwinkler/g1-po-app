// --- START OF FILE SupplierList.jsx ---

import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './SupplierList.css';

function SupplierList() {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const fetchSuppliers = useCallback(async () => {
    setLoading(true);
    setError(null);
    // Construct the full absolute URL
    const relativePath = '/suppliers';
    const fullApiUrl = `${import.meta.env.VITE_API_BASE_URL}${relativePath}`;
    console.log("SupplierList.jsx: Fetching suppliers from:", fullApiUrl);

    try {
      const response = await fetch(fullApiUrl); // Use fullApiUrl
      if (!response.ok) {
        let errorMsg = `HTTP error! Status: ${response.status}`;
        try {
          const errorData = await response.json();
          errorMsg = errorData.message || errorData.error || errorMsg;
        } catch (e) { /* Ignore if response not json */ }
        throw new Error(errorMsg);
      }
      const data = await response.json();
      setSuppliers(data || []);
    } catch (err) {
      console.error("Error fetching suppliers:", err);
      setError(err.message);
      setSuppliers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSuppliers();
  }, [fetchSuppliers]);

  const handleRowClick = (supplierId) => {
    navigate(`/suppliers/edit/${supplierId}`);
  };

  const handleLinkClick = (e) => {
    e.stopPropagation(); // Prevent row click when clicking the edit link
  };

  if (loading) return <div className="loading-message">Loading suppliers...</div>;

  return (
    <div className="list-view-container">
      <h2>Suppliers</h2>

      <div className="controls-container" style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
        <Link to="/suppliers/add" className="add-new-button">Add New Supplier</Link>
      </div>

      {error && <div className="error-message" style={{ marginBottom: '15px' }}>Error loading suppliers: {error}</div>}

      {suppliers.length === 0 && !loading ? (
        <p className="empty-list-message">No suppliers found.</p>
      ) : (
        <div className="table-responsive-container">
          <table className="data-table">
            {/* Desktop Table Headers */}
            <thead>
              <tr>
                <th>Name</th>
                <th>Contact Person</th>
                <th>Location</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map(supplier => (
                <tr
                  key={supplier.id}
                  className="clickable-row"
                  onClick={() => handleRowClick(supplier.id)}
                  title="Edit Supplier"
                >
                  {/* For Mobile Card: This td's ::before label will be hidden by CSS */}
                  <td data-label="Name" className="supplier-name-card-cell">
                    <div className="supplier-name-value">{supplier.name}</div>
                  </td>

                  {/* For Mobile Card: This td's ::before label will be hidden by CSS */}
                  <td data-label="Contact" className="supplier-contact-card-cell">
                    {supplier.contact_person ? (
                      <div className="supplier-contact-value">{supplier.contact_person}</div>
                    ) : (
                      <div className="supplier-contact-value"></div> // Ensures cell structure even if empty for mobile
                    )}
                  </td>
                  
                  {/* For Mobile Card: This td's ::before label will be hidden by CSS */}
                  <td data-label="Location" className="supplier-location-card-cell">
                    {(supplier.city || supplier.state) ? (
                      <div className="supplier-location-value">
                        {supplier.city || ''}{supplier.city && supplier.state ? ', ' : ''}{supplier.state || ''}
                      </div>
                    ) : (
                      <div className="supplier-location-value"></div> // Ensures cell structure even if empty for mobile
                    )}
                  </td>

                  {/* Fields not shown on card (email, payment_terms, created_at, updated_at) are omitted here */}
                  {/* If you need them for desktop, add more <th> and corresponding <td> below, hidden on mobile via CSS if necessary */}

                  <td data-label="Actions" className="supplier-actions-cell">
                    <Link to={`/suppliers/edit/${supplier.id}`} onClick={handleLinkClick} className="action-link">
                      Edit
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default SupplierList;
// --- END OF FILE SupplierList.jsx ---