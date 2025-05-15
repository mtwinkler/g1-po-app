// SupplierList.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './SupplierList.css'; // Assuming you have styles for this list
import { useAuth } from '../contexts/AuthContext'; // Import useAuth

function SupplierList() {
  const { currentUser, loading: authLoading } = useAuth(); // Get currentUser and auth loading state
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true); // For loading supplier data
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const fetchSuppliers = useCallback(async (signal) => {
    if (!currentUser) {
      setSuppliers([]); // Clear data if no user
      setLoading(false);
      // setError("Please log in to view suppliers."); // Error will be set by useEffect or ProtectedRoute
      return;
    }
    setLoading(true);
    setError(null);
    const relativePath = '/suppliers';
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("SupplierList.jsx: Fetching suppliers from:", fullApiUrl);

    try {
      const token = await currentUser.getIdToken(true); // Get Firebase ID token
      const response = await fetch(fullApiUrl, {
        signal,
        headers: {
          'Authorization': `Bearer ${token}` // Add Authorization header
        }
      });
      if (signal && signal.aborted) return;

      if (!response.ok) {
        let errorMsg = `Failed to load suppliers. Status: ${response.status}`;
        if (response.status === 401 || response.status === 403) {
            errorMsg = "Unauthorized to fetch suppliers. Your session might have expired.";
            // navigate('/login'); // Optional: redirect if session truly expired
        } else {
            try { const errorData = await response.json(); errorMsg = errorData.message || errorData.error || errorMsg; } catch (e) {}
        }
        throw new Error(errorMsg);
      }
      const data = await response.json();
      if (signal && signal.aborted) return;
      setSuppliers(data || []);
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error fetching suppliers:", err);
        setError(err.message);
        setSuppliers([]);
      }
    } finally {
      if (!signal || !signal.aborted) setLoading(false);
    }
  }, [VITE_API_BASE_URL, currentUser, navigate]); // Added currentUser and navigate

  useEffect(() => {
    if (authLoading) { // Wait for Firebase auth state to resolve
        setLoading(true); // Keep the list loading
        return;
    }
    if (currentUser) {
      const abortController = new AbortController();
      fetchSuppliers(abortController.signal);
      return () => abortController.abort();
    } else {
      // No user, clear data and stop loading, set appropriate error
      setSuppliers([]);
      setLoading(false);
      setError("Please log in to view suppliers.");
    }
  }, [currentUser, authLoading, fetchSuppliers]); // Added authLoading

  const handleRowClick = (supplierId) => {
    if (currentUser) { // Only navigate if user is logged in
        navigate(`/suppliers/edit/${supplierId}`);
    } else {
        setError("Please log in to edit suppliers."); // Should ideally not happen if page is protected
    }
  };

  const handleLinkClick = (e) => {
    if (!currentUser) {
        e.preventDefault(); // Prevent navigation if not logged in
        setError("Please log in to perform this action.");
        return;
    }
    e.stopPropagation(); // Allow link navigation if user is logged in
  };

  if (authLoading) { // Show a generic loading if auth state is not yet resolved
    return <div className="loading-message list-view-container">Loading session...</div>;
  }

  // This page should be protected by ProtectedRoute,
  // but these checks provide graceful UI if it's somehow rendered without a user.
  if (!currentUser && !authLoading) {
    return (
        <div className="list-view-container">
            <h2>Suppliers</h2>
            <div className="error-message">Please <Link to="/login">log in</Link> to view suppliers.</div>
        </div>
    );
  }
  
  // If user is logged in, but data is still loading for the first time
  if (loading && currentUser && suppliers.length === 0) {
    return <div className="loading-message list-view-container">Loading suppliers...</div>;
  }

  // If there was an error fetching data (and user is logged in)
  if (error && currentUser) {
     return (
        <div className="list-view-container">
            <h2>Suppliers</h2>
            <div className="error-message">Error loading suppliers: {error}</div>
            {/* Still show add button if error is just for fetching list, and user is logged in */}
            {currentUser && (
                 <div className="controls-container" style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
                    <Link to="/suppliers/add" className="add-new-button">Add New Supplier</Link>
                </div>
            )}
        </div>
     );
  }

  return (
    <div className="list-view-container">
      <h2>Suppliers</h2>

      {currentUser && ( // Only show controls if user is logged in
        <div className="controls-container" style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
            <Link to="/suppliers/add" className="add-new-button">Add New Supplier</Link>
        </div>
      )}

      {/* Show specific fetch error only if data hasn't loaded and it's not a "please log in" type error */}
      {error && suppliers.length === 0 && !loading && (!error.toLowerCase().includes("log in")) && <div className="error-message">Error: {error}</div>}

      {suppliers.length === 0 && !loading && !error ? (
        <p className="empty-list-message">No suppliers found. <Link to="/suppliers/add">Add one now?</Link></p>
      ) : suppliers.length > 0 && !error && ( // Ensure suppliers exist and no error
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
