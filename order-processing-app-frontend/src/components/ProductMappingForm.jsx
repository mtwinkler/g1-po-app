// --- START OF FILE ProductMappingForm.jsx ---

import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import './ProductMappingForm.css';

function ProductMappingForm() {
  const [formData, setFormData] = useState({
    sku: '',
    standard_description: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({
      ...prevState,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    // Construct the full absolute URL
    const relativePath = '/products';
    const fullApiUrl = `${import.meta.env.VITE_API_BASE_URL}${relativePath}`;
    console.log("ProductMappingForm.jsx: Submitting POST to:", fullApiUrl);

    try {
      const response = await fetch(fullApiUrl, { // Use fullApiUrl
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });
      const responseData = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(responseData?.message || `HTTP error! Status: ${response.status}`);
      }
      setSuccessMessage('Mapping added successfully! Redirecting...');
      setTimeout(() => {
        navigate('/products');
      }, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

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
            disabled={submitting}
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
            disabled={submitting}
            rows="6"
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button primary" disabled={submitting}>
            {submitting ? 'Creating...' : 'Create Mapping'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default ProductMappingForm;
// --- END OF FILE ProductMappingForm.jsx ---