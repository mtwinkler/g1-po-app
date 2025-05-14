// --- START OF FILE EditProductMappingForm.jsx ---

import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import './EditProductMappingForm.css';

function EditProductMappingForm() {
  const [formData, setFormData] = useState({ sku: '', standard_description: '' });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();
  const { productId } = useParams();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  useEffect(() => {
    const fetchProductMapping = async () => {
      setLoading(true);
      setError(null);
      const relativePath = `/products/${productId}`;
      const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
      console.log("EditProductMappingForm.jsx: Fetching mapping from:", fullApiUrl);

      try {
        const response = await fetch(fullApiUrl); // Use fullApiUrl
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ message: `HTTP error! Status: ${response.status}` }));
          throw new Error(errorData.message || `HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
        setFormData({ sku: data.sku || '', standard_description: data.standard_description || '' });
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    if (productId) {
        fetchProductMapping();
    } else {
        setError("Product ID is missing.");
        setLoading(false);
    }
  }, [productId, VITE_API_BASE_URL]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({ ...prevState, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const relativePath = `/products/${productId}`;
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("EditProductMappingForm.jsx: Submitting PUT to:", fullApiUrl);

    try {
      const response = await fetch(fullApiUrl, { // Use fullApiUrl
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      const responseData = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(responseData?.message || `HTTP error! Status: ${response.status}`);
      }
      setSuccessMessage('Mapping updated successfully! Redirecting...');
      setTimeout(() => navigate('/products'), 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="form-page-container"><div className="form-message loading">Loading product mapping data...</div></div>;

  return (
    <div className="form-page-container">
      <h2>Edit Product Mapping (ID: {productId})</h2>
      <Link to="/products" className="form-back-link">← Back to Mappings List</Link>

      {error && <div className="form-message error">Error: {error}</div>}
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
            disabled={submitting || loading}
          />
        </div>
        <div className="form-group">
          <label htmlFor="standard_description">Standard Description:</label>
          <input // Changed to input as per your original, use textarea if preferred
            type="text"
            id="standard_description"
            name="standard_description"
            value={formData.standard_description}
            onChange={handleChange}
            required
            disabled={submitting || loading}
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button warning" disabled={submitting || loading}>
            {submitting ? 'Updating...' : 'Update Mapping'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default EditProductMappingForm;
// --- END OF FILE EditProductMappingForm.jsx ---