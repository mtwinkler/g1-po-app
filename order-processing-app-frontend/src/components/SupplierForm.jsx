// --- START OF FILE SupplierForm.jsx ---

import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './SupplierForm.css';

function SupplierForm() {
  const [formData, setFormData] = useState({
    name: '', email: '', payment_terms: '', address_line1: '',
    address_line2: '', city: '', state: '', zip: '', country: '',
    phone: '', contact_person: '', defaultponotes: ''
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({ ...prevState, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const relativePath = '/suppliers';
    const fullApiUrl = `${import.meta.env.VITE_API_BASE_URL}${relativePath}`;
    console.log("SupplierForm.jsx: Submitting POST to:", fullApiUrl);

    try {
      const response = await fetch(fullApiUrl, { // Use fullApiUrl
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData), // Assuming backend handles casing correctly
      });

      const responseData = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(responseData?.message || `HTTP error! Status: ${response.status}`);
      }
      setSuccessMessage('Supplier added successfully! Redirecting...');
      setTimeout(() => { navigate('/suppliers'); }, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="form-page-container">
      <h2>Add New Supplier</h2>
      <Link to="/suppliers" className="form-back-link">← Back to Suppliers List</Link>

      {submitting && <div className="form-message loading">Submitting...</div>}
      {error && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="name">Name:</label>
          <input type="text" id="name" name="name" value={formData.name} onChange={handleChange} required disabled={submitting}/>
        </div>
        <div className="form-group">
          <label htmlFor="email">Email:</label>
          <input type="email" id="email" name="email" value={formData.email} onChange={handleChange} required disabled={submitting}/>
        </div>
        <div className="form-group">
          <label htmlFor="payment_terms">Payment Terms:</label>
          <input type="text" id="payment_terms" name="payment_terms" value={formData.payment_terms} onChange={handleChange} disabled={submitting}/>
        </div>
        <div className="form-group">
           <label htmlFor="address_line1">Address Line 1:</label>
           <input type="text" id="address_line1" name="address_line1" value={formData.address_line1} onChange={handleChange} disabled={submitting}/>
         </div>
        <div className="form-group">
           <label htmlFor="address_line2">Address Line 2:</label>
           <input type="text" id="address_line2" name="address_line2" value={formData.address_line2} onChange={handleChange} disabled={submitting}/>
         </div>
         <div className="form-group">
           <label htmlFor="city">City:</label>
           <input type="text" id="city" name="city" value={formData.city} onChange={handleChange} disabled={submitting}/>
         </div>
          <div className="form-group">
           <label htmlFor="state">State:</label>
           <input type="text" id="state" name="state" value={formData.state} onChange={handleChange} disabled={submitting}/>
         </div>
         <div className="form-group">
           <label htmlFor="zip">Zip Code:</label>
           <input type="text" id="zip" name="zip" value={formData.zip} onChange={handleChange} disabled={submitting}/>
         </div>
          <div className="form-group">
           <label htmlFor="country">Country:</label>
           <input type="text" id="country" name="country" value={formData.country} onChange={handleChange} disabled={submitting}/>
         </div>
         <div className="form-group">
           <label htmlFor="phone">Phone:</label>
           <input type="text" id="phone" name="phone" value={formData.phone} onChange={handleChange} disabled={submitting}/>
         </div>
          <div className="form-group">
           <label htmlFor="contact_person">Contact Person:</label>
           <input type="text" id="contact_person" name="contact_person" value={formData.contact_person} onChange={handleChange} disabled={submitting}/>
         </div>
        <div className="form-group">
          <label htmlFor="defaultponotes">Default PO Notes:</label>
          <textarea
            id="defaultponotes"
            name="defaultponotes"
            value={formData.defaultponotes}
            onChange={handleChange}
            disabled={submitting}
            rows="3"
            placeholder="Enter default note for Purchase Orders to this supplier..."
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button primary" disabled={submitting}>
            {submitting ? 'Creating...' : 'Create Supplier'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default SupplierForm;
// --- END OF FILE SupplierForm.jsx ---