// EditSupplierForm.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import './EditSupplierForm.css'; // Assuming CSS is named EditSupplierForm.css or reuse SupplierForm.css
import { useAuth } from '../contexts/AuthContext'; 

function EditSupplierForm() {
  const { supplierId } = useParams(); 
  const { currentUser, loading: authLoading, apiService } = useAuth(); // Use apiService
  const [formData, setFormData] = useState({
    name: '', email: '', payment_terms: '', address_line1: '',
    address_line2: '', city: '', state: '', zip: '', country: '',
    phone: '', contact_person: '', defaultponotes: ''
  });
  const [initialLoading, setInitialLoading] = useState(true); 
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();
  // VITE_API_BASE_URL is not needed here as apiService handles it.

  const fetchSupplierData = useCallback(async (signal) => {
    if (!currentUser || !apiService || !supplierId) { 
      setError(currentUser ? "Supplier ID is missing or API service unavailable." : "Please log in.");
      setInitialLoading(false);
      return;
    }
    setInitialLoading(true);
    setError(null);
    const relativePath = `/suppliers/${supplierId}`; // API endpoint path
    console.log("EditSupplierForm.jsx: Fetching supplier from API via apiService:", relativePath);
    try {
      // Use apiService.get()
      const data = await apiService.get(relativePath, {}, { signal });
      setFormData({
        name: data.name || '',
        email: data.email || '',
        payment_terms: data.payment_terms || '',
        address_line1: data.address_line1 || '',
        address_line2: data.address_line2 || '',
        city: data.city || '',
        state: data.state || '',
        zip: data.zip || '',
        country: data.country || '',
        phone: data.phone || '',
        contact_person: data.contact_person || '',
        defaultponotes: data.defaultponotes || ''
      });
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error fetching supplier data:", err);
        setError(err.data?.message || err.message || "Failed to load supplier data.");
      }
    } finally {
      if (!signal || !signal.aborted) {
        setInitialLoading(false);
      }
    }
  }, [supplierId, currentUser, apiService]); // apiService added

  useEffect(() => {
    if (authLoading) return; 
    const abortController = new AbortController();
    if (currentUser && supplierId) {
      fetchSupplierData(abortController.signal);
    } else if (!currentUser) {
      setError("Please log in to edit suppliers.");
      setInitialLoading(false);
    }
     return () => abortController.abort();
  }, [supplierId, currentUser, authLoading, fetchSupplierData]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({ ...prevState, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!currentUser || !apiService) {
      setError("Please log in to update the supplier. API service is unavailable.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');
    const relativePath = `/suppliers/${supplierId}`; // API endpoint path
    console.log("EditSupplierForm.jsx: Submitting PUT to API via apiService:", relativePath);

    try {
      // Use apiService.put()
      const responseData = await apiService.put(relativePath, formData);
      setSuccessMessage(responseData?.message || 'Supplier updated successfully! Redirecting...');
      setTimeout(() => {
        // Corrected navigation path
        navigate('/utils/suppliers'); 
      }, 1500);
    } catch (err) {
      let errorMsg = err.data?.message || err.message || "An unexpected error occurred.";
       if (err.status === 401 || err.status === 403) {
          errorMsg = "Unauthorized to update supplier. Please log in again.";
      }
      setError(errorMsg);
      console.error("Error updating supplier:", err);
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || initialLoading) {
    return <div className="form-page-container"><div className="form-message loading">Loading...</div></div>;
  }

  if (!currentUser) {
    return (
      <div className="form-page-container">
        <h2>Edit Supplier</h2>
        <div className="form-message error">Please <Link to="/login">log in</Link> to edit suppliers.</div>
      </div>
    );
  }
  
  if (error && !formData.name && !initialLoading) { 
    return (
         <div className="form-page-container">
            <h2>Edit Supplier</h2>
            {/* Corrected link path */}
            <Link to="/utils/suppliers" className="form-back-link">← Back to Suppliers List</Link>
            <div className="form-message error">Error: {error}</div>
        </div>
    );
  }

  return (
    <div className="edit-supplier-form-container form-page-container"> 
      <h2>Edit Supplier (ID: {supplierId})</h2>
      {/* Corrected link path */}
      <Link to="/utils/suppliers" className="form-back-link">← Back to Suppliers List</Link>

      {submitting && <div className="form-message loading">Submitting changes...</div>}
      {error && !initialLoading && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="name">Name:</label>
          <input type="text" id="name" name="name" value={formData.name || ''} onChange={handleChange} required disabled={submitting || initialLoading || !currentUser} />
        </div>
        <div className="form-group">
          <label htmlFor="email">Email:</label>
          <input type="email" id="email" name="email" value={formData.email || ''} onChange={handleChange} required disabled={submitting || initialLoading || !currentUser} />
        </div>
        <div className="form-group">
          <label htmlFor="payment_terms">Payment Terms:</label>
          <input type="text" id="payment_terms" name="payment_terms" value={formData.payment_terms || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
        </div>
         <div className="form-group">
           <label htmlFor="address_line1">Address Line 1:</label>
           <input type="text" id="address_line1" name="address_line1" value={formData.address_line1 || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="address_line2">Address Line 2:</label>
           <input type="text" id="address_line2" name="address_line2" value={formData.address_line2 || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="city">City:</label>
           <input type="text" id="city" name="city" value={formData.city || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="state">State:</label>
           <input type="text" id="state" name="state" value={formData.state || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="zip">Zip:</label>
           <input type="text" id="zip" name="zip" value={formData.zip || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="country">Country:</label>
           <input type="text" id="country" name="country" value={formData.country || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="phone">Phone:</label>
           <input type="text" id="phone" name="phone" value={formData.phone || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="contact_person">Contact Person:</label>
           <input type="text" id="contact_person" name="contact_person" value={formData.contact_person || ''} onChange={handleChange} disabled={submitting || initialLoading || !currentUser} />
         </div>
         <div className="form-group">
            <label htmlFor="defaultponotes">Default PO Notes:</label>
            <textarea id="defaultponotes" name="defaultponotes" value={formData.defaultponotes || ''} onChange={handleChange} rows="3" disabled={submitting || initialLoading || !currentUser} />
         </div>

        <div className="form-actions">
            <button type="submit" className="form-button" disabled={submitting || initialLoading || !currentUser}> 
                {submitting ? 'Updating...' : 'Update Supplier'}
            </button>
        </div>
      </form>
    </div>
  );
}

export default EditSupplierForm;
