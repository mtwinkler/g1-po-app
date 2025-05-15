// ProductMappingForm.jsx
import React, { useState, useEffect } from 'react'; // Added useEffect for authLoading check
import { useNavigate, Link } from 'react-router-dom';
import './ProductMappingForm.css'; // Assuming you have styles for this form
import { useAuth } from '../contexts/AuthContext'; // Import useAuth

function ProductMappingForm() {
  const { currentUser, loading: authLoading } = useAuth(); // Get currentUser and auth loading state
  const [formData, setFormData] = useState({
    sku: '',
    standard_description: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({
      ...prevState,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!currentUser) {
        setError("Please log in to add a product mapping.");
        return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const relativePath = '/products';
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("ProductMappingForm.jsx: Submitting POST to:", fullApiUrl);

    try {
      const token = await currentUser.getIdToken(true); // Get Firebase ID token
      const response = await fetch(fullApiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}` // Add Authorization header
        },
        body: JSON.stringify(formData),
      });
      const responseData = await response.json().catch(() => null); // Try to parse JSON even on error
      if (!response.ok) {
        let errorMsg = responseData?.message || `HTTP error! Status: ${response.status}`;
        if (response.status === 401 || response.status === 403) {
            errorMsg = "Unauthorized to add mapping. Please log in again.";
            // navigate('/login'); // Optional: redirect
        }
        throw new Error(errorMsg);
      }
      setSuccessMessage('Mapping added successfully! Redirecting...');
      setFormData({ sku: '', standard_description: '' }); // Clear form on success
      setTimeout(() => {
        navigate('/products');
      }, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // Effect to clear messages if user logs out while on this page
  useEffect(() => {
    if (!authLoading && !currentUser) {
        setError("Please log in to access this page.");
        setSuccessMessage(''); // Clear any previous success messages
    }
  }, [currentUser, authLoading]);


  if (authLoading) {
    return <div className="form-page-container"><div className="form-message loading">Loading session...</div></div>;
  }

  // This page should be protected by ProtectedRoute, but as an additional check:
  if (!currentUser) {
    return (
        <div className="form-page-container">
            <h2>Add New Product Mapping</h2>
            <div className="form-message error">Please <Link to="/login">log in</Link> to add a new product mapping.</div>
        </div>
    );
  }

  return (
    <div className="form-page-container">
      <h2>Add New Product Mapping</h2>
      <Link to="/products" className="form-back-link">← Back to Mappings List</Link>

      {submitting && <div className="form-message loading">Submitting...</div>}
      {error && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}

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
            disabled={submitting || !currentUser} // Disable if no user or submitting
          />
        </div>
        <div className="form-group">
          <label htmlFor="standard_description">Standard Description:</label>
          <textarea
            id="standard_description"
            name="standard_description"
            value={formData.standard_description}
            onChange={handleChange}
            required
            disabled={submitting || !currentUser} // Disable if no user or submitting
            rows="6"
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button primary" disabled={submitting || !currentUser}>
            {submitting ? 'Creating...' : 'Create Mapping'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default ProductMappingForm;
