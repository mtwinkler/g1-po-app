// EditSupplierForm.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import './EditSupplierForm.css'; // Assuming you have styles for this form
import { useAuth } from '../contexts/AuthContext'; // Import useAuth

function EditSupplierForm() {
  const { currentUser, loading: authLoading } = useAuth(); // Get currentUser and auth loading state
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    payment_terms: '',
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    zip: '',
    country: '',
    phone: '',
    contact_person: '',
    defaultponotes: ''
  });
  const [loading, setLoading] = useState(true); // For loading initial supplier data
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(''); // Changed from 'success' boolean to string for messages
  const navigate = useNavigate();
  const { supplierId } = useParams();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const fetchSupplier = useCallback(async (signal) => {
    if (!currentUser) {
      setLoading(false);
      setError("Please log in to edit supplier details.");
      return;
    }
    setLoading(true);
    setError(null);
    const relativePath = `/suppliers/${supplierId}`;
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("EditSupplierForm.jsx: Fetching supplier from:", fullApiUrl);

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
        let errorMsg = `Failed to load supplier. Status: ${response.status}`;
        if (response.status === 401 || response.status === 403) {
            errorMsg = "Unauthorized to fetch supplier. Please log in again.";
            // navigate('/login'); // Optional: redirect
        } else {
            try { const errorData = await response.json(); errorMsg = errorData.message || errorData.error || errorMsg; } catch (e) {}
        }
        throw new Error(errorMsg);
      }
      const data = await response.json();
      if (signal && signal.aborted) return;
      // Ensure all fields in formData are initialized, even if not present in data
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
      if (err.name !== 'AbortError') setError(err.message);
    } finally {
      if (!signal || !signal.aborted) setLoading(false);
    }
  }, [supplierId, VITE_API_BASE_URL, currentUser, navigate]); // Added currentUser and navigate

  useEffect(() => {
    if (authLoading) {
        setLoading(true); // Keep form loading if auth state is resolving
        return;
    }
    if (currentUser && supplierId) {
      const abortController = new AbortController();
      fetchSupplier(abortController.signal);
      return () => abortController.abort();
    } else if (!currentUser && supplierId) {
        setError("Please log in to edit supplier details.");
        setLoading(false);
    } else if (!supplierId) {
        setError("Supplier ID is missing.");
        setLoading(false);
    }
  }, [supplierId, currentUser, authLoading, fetchSupplier]); // Added authLoading

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({ ...prevState, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!currentUser) {
        setError("Please log in to update supplier details.");
        return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const relativePath = `/suppliers/${supplierId}`;
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("EditSupplierForm.jsx: Submitting PUT to:", fullApiUrl);

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
      const responseData = await response.json().catch(() => null);
      if (!response.ok) {
        let errorMsg = responseData?.message || `HTTP error! Status: ${response.status}`;
        if (response.status === 401 || response.status === 403) {
            errorMsg = "Unauthorized to update supplier. Please log in again.";
            // navigate('/login'); // Optional: redirect
        }
        throw new Error(errorMsg);
      }
      setSuccessMessage('Supplier updated successfully! Redirecting...');
      setTimeout(() => navigate('/suppliers'), 1500);
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
            <h2>Edit Supplier</h2>
            <div className="form-message error">Please <Link to="/login">log in</Link> to edit supplier details.</div>
        </div>
    );
  }

  // If user is logged in, but initial data is still loading
  if (loading && currentUser) {
    return <div className="form-page-container"><div className="form-message loading">Loading supplier data...</div></div>;
  }
  
  // If there was an error fetching data (and user is logged in)
  // This error might be "Please log in..." if fetchSupplier was called before currentUser was set (though useEffect guards against this)
  if (error && currentUser && !formData.name) { // Show main fetch error only if form isn't populated
     return (
        <div className="form-page-container">
            <h2>Edit Supplier (ID: {supplierId})</h2>
            <Link to="/suppliers" className="form-back-link">← Back to Suppliers List</Link>
            <div className="form-message error">Error: {error}</div>
        </div>
     );
  }

  return (
    <div className="edit-supplier-form-container form-page-container"> {/* Added form-page-container for consistency */}
      <h2>Edit Supplier (ID: {supplierId})</h2>
      <Link to="/suppliers" className="form-back-link">← Back to Suppliers List</Link>

      {/* Display error specific to submit, or fetch error if form data is present */}
      {error && !loading && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}
      {submitting && !successMessage && <div className="form-message loading">Submitting updates...</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="name">Name:</label>
          <input type="text" id="name" name="name" value={formData.name || ''} onChange={handleChange} required disabled={submitting || loading || !currentUser} />
        </div>
        <div className="form-group">
          <label htmlFor="email">Email:</label>
          <input type="email" id="email" name="email" value={formData.email || ''} onChange={handleChange} required disabled={submitting || loading || !currentUser} />
        </div>
        <div className="form-group">
          <label htmlFor="payment_terms">Payment Terms:</label>
          <input type="text" id="payment_terms" name="payment_terms" value={formData.payment_terms || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
        </div>
         <div className="form-group">
           <label htmlFor="address_line1">Address Line 1:</label>
           <input type="text" id="address_line1" name="address_line1" value={formData.address_line1 || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="address_line2">Address Line 2:</label>
           <input type="text" id="address_line2" name="address_line2" value={formData.address_line2 || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="city">City:</label>
           <input type="text" id="city" name="city" value={formData.city || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="state">State:</label>
           <input type="text" id="state" name="state" value={formData.state || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="zip">Zip:</label>
           <input type="text" id="zip" name="zip" value={formData.zip || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="country">Country:</label>
           <input type="text" id="country" name="country" value={formData.country || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
         <div className="form-group">
           <label htmlFor="phone">Phone:</label>
           <input type="text" id="phone" name="phone" value={formData.phone || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
          <div className="form-group">
           <label htmlFor="contact_person">Contact Person:</label>
           <input type="text" id="contact_person" name="contact_person" value={formData.contact_person || ''} onChange={handleChange} disabled={submitting || loading || !currentUser} />
         </div>
         <div className="form-group">
            <label htmlFor="defaultponotes">Default PO Notes:</label>
            <textarea id="defaultponotes" name="defaultponotes" value={formData.defaultponotes || ''} onChange={handleChange} rows="3" disabled={submitting || loading || !currentUser} />
         </div>

        <div className="form-actions">
            <button type="submit" className="form-button" disabled={submitting || loading || !currentUser}> {/* Ensure consistent button class if needed */}
                {submitting ? 'Updating...' : 'Update Supplier'}
            </button>
        </div>
      </form>
    </div>
  );
}

export default EditSupplierForm;
