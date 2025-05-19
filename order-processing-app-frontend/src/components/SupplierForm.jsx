// SupplierForm.jsx
import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './SupplierForm.css'; 
import { useAuth } from '../contexts/AuthContext'; 

function SupplierForm() {
  const { currentUser, loading: authLoading, apiService } = useAuth(); 
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
    if (!currentUser || !apiService) { 
        setError("Please log in to add a new supplier. API service is unavailable.");
        return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const relativePath = '/suppliers'; 
    console.log("SupplierForm.jsx: Submitting POST to API via apiService:", relativePath, "with data:", formData);

    try {
      const responseData = await apiService.post(relativePath, formData);
      
      setSuccessMessage(responseData?.message ||'Supplier added successfully! Redirecting...');
      setFormData({ 
        name: '', email: '', payment_terms: '', address_line1: '',
        address_line2: '', city: '', state: '', zip: '', country: '',
        phone: '', contact_person: '', defaultponotes: ''
      });
      setTimeout(() => {
        // Corrected navigation path
        navigate('/utils/suppliers'); 
      }, 1500);
    } catch (err) {
      let errorMsg = err.data?.message || err.message || "An unexpected error occurred.";
      if (err.status === 401 || err.status === 403) {
          errorMsg = "Unauthorized to add supplier. Please log in again.";
      }
      setError(errorMsg);
      console.error("Error submitting supplier form:", err);
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    if (!authLoading && !currentUser) {
        setError("Please log in to access this page.");
        setSuccessMessage(''); 
    }
  }, [currentUser, authLoading]);


  if (authLoading) {
    return <div className="form-page-container"><div className="form-message loading">Loading session...</div></div>;
  }

  if (!currentUser) {
    return (
        <div className="form-page-container">
            <h2>Add New Supplier</h2>
            <div className="form-message error">Please <Link to="/login">log in</Link> to add a new supplier.</div>
        </div>
    );
  }

  return (
    <div className="form-page-container">
      <h2>Add New Supplier</h2>
      {/* Corrected link path */}
      <Link to="/utils/suppliers" className="form-back-link">← Back to Suppliers List</Link>

      {submitting && <div className="form-message loading">Submitting...</div>}
      {error && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="name">Name:</label>
          <input type="text" id="name" name="name" value={formData.name} onChange={handleChange} required disabled={submitting || !currentUser} />
        </div>
        <div className="form-group">
          <label htmlFor="email">Email:</label>
          <input type="email" id="email" name="email" value={formData.email} onChange={handleChange} required disabled={submitting || !currentUser} />
        </div>
        <div className="form-group">
          <label htmlFor="payment_terms">Payment Terms:</label>
          <input type="text" id="payment_terms" name="payment_terms" value={formData.payment_terms} onChange={handleChange} disabled={submitting || !currentUser} />
        </div>
        <div className="form-group">
           <label htmlFor="address_line1">Address Line 1:</label>
           <input type="text" id="address_line1" name="address_line1" value={formData.address_line1} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
        <div className="form-group">
           <label htmlFor="address_line2">Address Line 2:</label>
           <input type="text" id="address_line2" name="address_line2" value={formData.address_line2} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="city">City:</label>
           <input type="text" id="city" name="city" value={formData.city} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="state">State:</label>
           <input type="text" id="state" name="state" value={formData.state} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="zip">Zip Code:</label>
           <input type="text" id="zip" name="zip" value={formData.zip} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="country">Country:</label>
           <input type="text" id="country" name="country" value={formData.country} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="phone">Phone:</label>
           <input type="text" id="phone" name="phone" value={formData.phone} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="contact_person">Contact Person:</label>
           <input type="text" id="contact_person" name="contact_person" value={formData.contact_person} onChange={handleChange} disabled={submitting || !currentUser} />
         </div>
        <div className="form-group">
          <label htmlFor="defaultponotes">Default PO Notes:</label>
          <textarea
            id="defaultponotes"
            name="defaultponotes"
            value={formData.defaultponotes}
            onChange={handleChange}
            disabled={submitting || !currentUser}
            rows="3"
            placeholder="Enter default note for Purchase Orders to this supplier..."
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button primary" disabled={submitting || !currentUser}>
            {submitting ? 'Creating...' : 'Create Supplier'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default SupplierForm;
