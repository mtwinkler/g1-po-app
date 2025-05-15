// ProductMappingList.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './ProductMappingList.css'; // Assuming you have styles for this list
import { useAuth } from '../contexts/AuthContext'; // Import useAuth

function ProductMappingList() {
  const { currentUser, loading: authLoading } = useAuth(); // Get currentUser and auth loading state
  const [productMappings, setProductMappings] = useState([]);
  const [loading, setLoading] = useState(true); // For loading mapping data
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const fetchProductMappings = useCallback(async (signal) => {
    if (!currentUser) {
      setProductMappings([]);
      setLoading(false);
      // setError("Please log in to view product mappings."); // Error will be set by useEffect or ProtectedRoute
      return;
    }
    setLoading(true);
    setError(null);
    const relativePath = '/products';
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("ProductMappingList.jsx: Fetching mappings from:", fullApiUrl);

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
        let errorMsg = `Failed to load mappings. Status: ${response.status}`;
        if (response.status === 401 || response.status === 403) {
            errorMsg = "Unauthorized to fetch mappings. Please log in again.";
            // navigate('/login'); // Optional: redirect
        } else {
            try { const errorData = await response.json(); errorMsg = errorData.message || errorData.error || errorMsg; } catch (e) {}
        }
        throw new Error(errorMsg);
      }
      const data = await response.json();
      if (signal && signal.aborted) return;
      setProductMappings(data || []);
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error fetching product mappings:", err);
        setError(err.message);
        setProductMappings([]);
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
      fetchProductMappings(abortController.signal);
      return () => abortController.abort();
    } else {
      // No user, clear data and stop loading
      setProductMappings([]);
      setLoading(false);
      setError("Please log in to view product mappings."); // Set error if no user after auth resolves
    }
  }, [currentUser, authLoading, fetchProductMappings]); // Added authLoading

  const handleRowClick = (mappingId) => {
    if (currentUser) { // Only navigate if user is logged in
        navigate(`/products/edit/${mappingId}`);
    } else {
        setError("Please log in to edit mappings.");
    }
  };

  const handleLinkClick = (e) => {
    if (!currentUser) {
        e.preventDefault(); // Prevent navigation if not logged in
        setError("Please log in to edit mappings.");
        return;
    }
    e.stopPropagation(); // Allow link navigation if user is logged in
  };

  if (authLoading) {
    return <div className="loading-message">Loading session...</div>;
  }

  // This page should be protected by ProtectedRoute,
  // but these checks provide graceful UI if it's somehow rendered without a user.
  if (!currentUser && !authLoading) {
    return (
        <div className="list-view-container">
            <h2>Product SKU Mappings</h2>
            <div className="error-message">Please <Link to="/login">log in</Link> to view product mappings.</div>
        </div>
    );
  }
  
  // If user is logged in, but data is still loading
  if (loading && currentUser) {
    return <div className="loading-message">Loading product mappings...</div>;
  }

  // If there was an error fetching data (and user is logged in)
  if (error && currentUser) {
     return (
        <div className="list-view-container">
            <h2>Product SKU Mappings</h2>
            <div className="error-message">Error loading mappings: {error}</div>
            <div className="controls-container">
                {/* Still show add button if error is just for fetching list */}
                <Link to="/products/add" className="add-new-button">Add New Mapping</Link>
            </div>
        </div>
     );
  }


  return (
    <div className="list-view-container">
      <h2>Product SKU Mappings</h2>

      <div className="controls-container">
        {/* The Link component itself doesn't have a disabled prop in the same way as buttons.
            Navigation will be handled by ProtectedRoute for the target page.
            If you wanted to visually disable it, you'd need custom CSS based on !currentUser.
            However, since this whole component is typically wrapped by ProtectedRoute,
            currentUser should be present.
        */}
        <Link to="/products/add" className="add-new-button">Add New Mapping</Link>
      </div>

      {/* Show error only if it's not a "please log in" type error already handled */}
      {error && (!error.toLowerCase().includes("log in")) && <div className="error-message">Error: {error}</div>}

      {productMappings.length === 0 && !loading && !error ? (
        <p className="empty-list-message">No product mappings found.</p>
      ) : productMappings.length > 0 && !error && ( // Ensure mappings exist and no error
        <div className="table-responsive-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Standard Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {productMappings.map(mapping => (
                  <tr
                    key={mapping.id}
                    className="clickable-row"
                    onClick={() => handleRowClick(mapping.id)}
                    title="Edit Mapping"
                  >
                    <td data-label="SKU">{mapping.sku}</td>
                    <td data-label="Description">{mapping.standard_description}</td>
                    <td data-label="Actions">
                      <Link to={`/products/edit/${mapping.id}`} onClick={handleLinkClick} className="action-link">
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

export default ProductMappingList;
