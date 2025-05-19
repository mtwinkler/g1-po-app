// SupplierList.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './SupplierList.css'; 
import { useAuth } from '../contexts/AuthContext'; 

function SupplierList() {
  const { currentUser, loading: authLoading, apiService } = useAuth(); // Use apiService
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true); 
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  // VITE_API_BASE_URL is not needed here as apiService handles it.

  const fetchSuppliers = useCallback(async (signal) => {
    if (!currentUser || !apiService) { // Check for apiService
      setSuppliers([]); 
      setLoading(false);
      setError(currentUser ? "API service is unavailable." : "Please log in to view suppliers.");
      return;
    }
    setLoading(true);
    setError(null);
    const relativePath = '/suppliers'; // API endpoint path
    console.log("SupplierList.jsx: Fetching suppliers from API via apiService:", relativePath);

    try {
      // Use apiService.get() which handles token and base URL
      const data = await apiService.get(relativePath, {}, { signal }); 
      if (signal && signal.aborted) return;
      setSuppliers(data || []);
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error fetching suppliers:", err);
        // err.data.message or err.message should contain the error from apiService
        setError(err.data?.message || err.message || "Failed to load suppliers.");
        setSuppliers([]);
      }
    } finally {
      if (!signal || !signal.aborted) setLoading(false);
    }
  }, [currentUser, apiService]); // apiService added to dependencies

  useEffect(() => {
    if (authLoading) { 
        setLoading(true); 
        return;
    }
    if (currentUser) {
      const abortController = new AbortController();
      fetchSuppliers(abortController.signal);
      return () => abortController.abort();
    } else {
      setSuppliers([]);
      setLoading(false);
      setError("Please log in to view suppliers.");
    }
  }, [currentUser, authLoading, fetchSuppliers]); 

  const handleRowClick = (supplierId) => {
    if (currentUser) { 
        // Corrected navigation path
        navigate(`/utils/suppliers/edit/${supplierId}`); 
    } else {
        setError("Please log in to edit suppliers."); 
    }
  };

  const handleLinkClick = (e) => {
    if (!currentUser) {
        e.preventDefault(); 
        setError("Please log in to perform this action.");
        return;
    }
    e.stopPropagation(); 
  };

  if (authLoading) { 
    return <div className="loading-message list-view-container">Loading session...</div>;
  }

  if (!currentUser && !authLoading) {
    return (
        <div className="list-view-container">
            <h2>Suppliers</h2>
            <div className="error-message">Please <Link to="/login">log in</Link> to view suppliers.</div>
        </div>
    );
  }
  
  if (loading && currentUser && suppliers.length === 0) {
    return <div className="loading-message list-view-container">Loading suppliers...</div>;
  }

  if (error && currentUser) {
     return (
        <div className="list-view-container">
            <h2>Suppliers</h2>
            <div className="error-message">Error loading suppliers: {error}</div>
            {currentUser && (
                 <div className="controls-container" style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
                    {/* Corrected link path */}
                    <Link to="/utils/suppliers/add" className="add-new-button">Add New Supplier</Link>
                </div>
            )}
        </div>
     );
  }

  return (
    <div className="list-view-container">
      <h2>Suppliers</h2>

      {currentUser && ( 
        <div className="controls-container" style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
            {/* Corrected link path */}
            <Link to="/utils/suppliers/add" className="add-new-button">Add New Supplier</Link>
        </div>
      )}

      {error && suppliers.length === 0 && !loading && (!error.toLowerCase().includes("log in")) && <div className="error-message">Error: {error}</div>}

      {suppliers.length === 0 && !loading && !error ? (
        // Corrected link path
        <p className="empty-list-message">No suppliers found. <Link to="/utils/suppliers/add">Add one now?</Link></p>
      ) : suppliers.length > 0 && !error && ( 
        <div className="table-responsive-container">
          <table className="data-table">
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
                    <td data-label="Name" className="supplier-name-card-cell">
                        <div className="supplier-name-value">{supplier.name}</div>
                    </td>
                    <td data-label="Contact" className="supplier-contact-card-cell">
                        {supplier.contact_person ? (
                            <div className="supplier-contact-value">{supplier.contact_person}</div>
                        ) : (
                            <div className="supplier-contact-value"></div>
                        )}
                    </td>
                    <td data-label="Location" className="supplier-location-card-cell">
                        {(supplier.city || supplier.state) ? (
                            <div className="supplier-location-value">
                                {supplier.city || ''}{supplier.city && supplier.state ? ', ' : ''}{supplier.state || ''}
                            </div>
                        ) : (
                            <div className="supplier-location-value"></div>
                        )}
                    </td>
                    <td data-label="Actions" className="supplier-actions-cell">
                      {/* Corrected link path */}
                      <Link to={`/utils/suppliers/edit/${supplier.id}`} onClick={handleLinkClick} className="action-link">
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
