// EditProductMappingForm.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import './EditProductMappingForm.css'; // Assuming you have styles for this form
import { useAuth } from '../contexts/AuthContext'; // Import useAuth

function EditProductMappingForm() {
  const { currentUser, loading: authLoading } = useAuth(); // Get currentUser and auth loading state
  const [formData, setFormData] = useState({ sku: '', standard_description: '' });
  const [loading, setLoading] = useState(true); // For loading initial mapping data
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();
  const { productId } = useParams();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const fetchProductMapping = useCallback(async (signal) => {
    if (!currentUser) {
      setLoading(false);
      setError("Please log in to edit product mappings.");
      return;
    }
    setLoading(true);
    setError(null);
    const relativePath = `/products/${productId}`;
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("EditProductMappingForm.jsx: Fetching mapping from:", fullApiUrl);

    try {
      const token = await currentUser.getIdToken(true);
      const response = await fetch(fullApiUrl, {
        signal,
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (signal && signal.aborted) return;

      if (!response.ok) {
        let errorMsg = `Failed to load mapping. Status: ${response.status}`;
        if (response.status === 401 || response.status === 403) {
            errorMsg = "Unauthorized to fetch mapping. Please log in again.";
            // navigate('/login'); // Optional: redirect
        } else {
            try { const errorData = await response.json(); errorMsg = errorData.message || errorData.error || errorMsg; } catch (e) {}
        }
        throw new Error(errorMsg);
      }
      const data = await response.json();
      if (signal && signal.aborted) return;
      setFormData({ sku: data.sku || '', standard_description: data.standard_description || '' });
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message);
    } finally {
      if (!signal || !signal.aborted) setLoading(false);
    }
  }, [productId, VITE_API_BASE_URL, currentUser, navigate]); // Added currentUser and navigate

  useEffect(() => {
    if (authLoading) { // Wait for Firebase auth state to resolve
        setLoading(true); // Keep the form loading
        return;
    }
    if (currentUser && productId) {
      const abortController = new AbortController();
      fetchProductMapping(abortController.signal);
      return () => abortController.abort();
    } else if (!currentUser && productId) {
        setError("Please log in to edit product mappings.");
        setLoading(false);
    } else if (!productId) {
        setError("Product ID is missing.");
        setLoading(false);
    }
  }, [productId, currentUser, authLoading, fetchProductMapping]); // Added authLoading

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({ ...prevState, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!currentUser) {
        setError("Please log in to update mappings.");
        return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const relativePath = `/products/${productId}`;
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("EditProductMappingForm.jsx: Submitting PUT to:", fullApiUrl);

    try {
      const token = await currentUser.getIdToken(true);
      const response = await fetch(fullApiUrl, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(formData),
      });
      const responseData = await response.json().catch(() => null); // Try to parse JSON even on error
      if (!response.ok) {
        let errorMsg = responseData?.message || `HTTP error! Status: ${response.status}`;
        if (response.status === 401 || response.status === 403) {
            errorMsg = "Unauthorized to update mapping. Please log in again.";
            // navigate('/login'); // Optional: redirect
        }
        throw new Error(errorMsg);
      }
      setSuccessMessage('Mapping updated successfully! Redirecting...');
      setTimeout(() => navigate('/products'), 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading) {
    return <div className="form-page-container"><div className="form-message loading">Loading session...</div></div>;
  }

  if (!currentUser && !authLoading) { // Auth resolved, no user
    return (
        <div className="form-page-container">
            <h2>Edit Product Mapping</h2>
            <div className="form-message error">Please <Link to="/login">log in</Link> to edit product mappings.</div>
        </div>
    );
  }

  // If user is logged in, but initial data is still loading
  if (loading && currentUser) {
    return <div className="form-page-container"><div className="form-message loading">Loading product mapping data...</div></div>;
  }
  
  // If there was an error fetching data (and user is logged in)
  if (error && currentUser) {
     return (
        <div className="form-page-container">
            <h2>Edit Product Mapping (ID: {productId})</h2>
            <Link to="/products" className="form-back-link">← Back to Mappings List</Link>
            <div className="form-message error">Error: {error}</div>
        </div>
     );
  }


  return (
    <div className="form-page-container">
      <h2>Edit Product Mapping (ID: {productId})</h2>
      <Link to="/products" className="form-back-link">← Back to Mappings List</Link>

      {/* Display error specific to submit, not initial load if form is visible */}
      {error && !loading && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}
      {submitting && !successMessage && <div className="form-message loading">Submitting updates...</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="sku">SKU:</label>
          <input
            type="text"
            id="sku"
            name="sku"
            value={formData.sku}
            onChange={handleChange}
            required
            disabled={submitting || loading || !currentUser} // Disable if no user
          />
        </div>
        <div className="form-group">
          <label htmlFor="standard_description">Standard Description:</label>
          <input
            type="text"
            id="standard_description"
            name="standard_description"
            value={formData.standard_description}
            onChange={handleChange}
            required
            disabled={submitting || loading || !currentUser} // Disable if no user
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button warning" disabled={submitting || loading || !currentUser}>
            {submitting ? 'Updating...' : 'Update Mapping'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default EditProductMappingForm;
