// src/components/HpeDescriptionForm.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import './HpeDescriptionForm.css'; // Create or rename this CSS file
import { useAuth } from '../contexts/AuthContext';

function HpeDescriptionForm() {
  const { currentUser, loading: authLoading, apiService } = useAuth();
  const [formData, setFormData] = useState({
    option_pn: '',
    po_description: '',
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
    if (!currentUser) {
        setError("Please log in to add an HPE description mapping.");
        return;
    }
    if (!formData.option_pn.trim() || !formData.po_description.trim()) {
      setError("Both Option PN and PO Description are required.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const apiPath = '/hpe-descriptions';
    console.log("HpeDescriptionForm.jsx: Submitting POST to:", apiPath, "with data:", formData);

    try {
      // --- THIS IS THE CORRECTED CALL ---
      // Call the 'post' method on the apiService object
      // The second argument to apiService.post is the body data
      // The third argument (optional) is for other fetch options (like signal, if needed for POST)
      const responseData = await apiService.post(apiPath, formData); 
      // --- END OF CORRECTION ---
      
      // Assuming your backend POST returns the created object or a success message
      // and apiService.post returns the parsed JSON from that.
      // If the backend returns 201 Created with no body, responseData might be null or a specific object.
      // Your apiService.post in AuthContext.jsx handles 204 or content-length: 0.
      // Check what responseData contains if needed: console.log("Create response:", responseData);

      setSuccessMessage(responseData?.message || 'HPE Mapping added successfully! Redirecting...');
      setFormData({ option_pn: '', po_description: '' }); // Clear form
      setTimeout(() => {
        navigate('/admin/hpe-descriptions'); 
      }, 1500);
    } catch (err) {
      console.error("Error adding HPE mapping:", err);
      setError(err.message || "Failed to add HPE mapping. Please try again.");
      // If err.data contains more specific errors from backend, you could display those:
      // if (err.data && err.data.error_type === 'DuplicateOptionPN') {
      //   setError(err.data.message); 
      // } else {
      //   setError(err.message || "Failed to add HPE mapping. Please try again.");
      // }
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
        <h2>Add New HPE PO Description Mapping</h2>
        <div className="form-message error">Please <Link to="/login">log in</Link> to add a new mapping.</div>
      </div>
    );
  }

  return (
    <div className="form-page-container">
      <h2>Add New PO Description</h2>
      <Link to="/admin/hpe-descriptions" className="form-back-link">← Back to HPE Mappings List</Link>

      {submitting && <div className="form-message loading">Submitting...</div>}
      {error && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="option_pn">Option PN:</label>
          <input
            type="text"
            id="option_pn"
            name="option_pn"
            value={formData.option_pn}
            onChange={handleChange}
            required
            disabled={submitting}
          />
        </div>
        <div className="form-group">
          <label htmlFor="po_description">PO Description:</label>
          <textarea
            id="po_description"
            name="po_description"
            value={formData.po_description}
            onChange={handleChange}
            required
            disabled={submitting}
            rows="6"
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button primary" disabled={submitting}>
            {submitting ? 'Creating...' : 'Create HPE Mapping'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default HpeDescriptionForm;