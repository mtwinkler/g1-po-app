// src/components/EditHpeDescriptionForm.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import './EditHpeDescriptionForm.css'; 
import { useAuth } from '../contexts/AuthContext';

function EditHpeDescriptionForm() {
  const { currentUser, loading: authLoading, apiService } = useAuth();
  const [initialOptionPn, setInitialOptionPn] = useState(''); 
  const [formData, setFormData] = useState({ po_description: '' });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();
  const { optionPnParam } = useParams();

  const fetchHpeMapping = useCallback(async (passedSignal) => {
    if (!currentUser || !optionPnParam) {
      setLoading(false);
      setError(currentUser ? "Option PN is missing." : "Please log in.");
      return;
    }
    setLoading(true);
    setError(null);
    
    const apiPath = `/hpe-descriptions/${encodeURIComponent(optionPnParam)}`;
    console.log("EditHpeDescriptionForm.jsx: Fetching HPE mapping from:", apiPath);

    try {
      // --- CORRECTED CALL ---
      const data = await apiService.get(
          apiPath, 
          {}, /* queryParams if any, none for fetching single item by ID */ 
          { signal: passedSignal } /* options object with signal */
      ); 
      // --- END OF CORRECTION ---

      if (passedSignal && passedSignal.aborted) return;
      
      setInitialOptionPn(data.option_pn || ''); 
      setFormData({ po_description: data.po_description || '' });
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error fetching HPE mapping for edit:", err);
        setError(err.message || "Failed to load HPE mapping data.");
      } else {
        console.log("EditHpeDescriptionForm.jsx: Fetch for edit aborted.");
      }
    } finally {
      if (!passedSignal || !passedSignal.aborted) setLoading(false);
    }
  }, [optionPnParam, currentUser, apiService]);

  useEffect(() => {
    if (authLoading) {
      setLoading(true);
      return;
    }
    if (currentUser && optionPnParam) {
      const abortController = new AbortController();
      fetchHpeMapping(abortController.signal);
      return () => abortController.abort();
    } else if (!currentUser && !authLoading) {
      setError("Please log in to edit HPE mappings.");
      setLoading(false);
    } else if (!optionPnParam) {
      setError("Option PN parameter is missing from URL.");
      setLoading(false);
    }
  }, [optionPnParam, currentUser, authLoading, fetchHpeMapping]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({ ...prevState, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!currentUser) {
      setError("Please log in to update HPE mappings.");
      return;
    }
     if (!formData.po_description.trim()) {
      setError("PO Description is required.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccessMessage('');

    const apiPath = `/hpe-descriptions/${encodeURIComponent(optionPnParam)}`;
    console.log("EditHpeDescriptionForm.jsx: Submitting PUT to:", apiPath, "with data:", formData);

    try {
      const bodyData = { po_description: formData.po_description };

      // --- CORRECTED CALL ---
      // Assuming you have an apiService.put method defined in AuthContext.jsx
      // similar to apiService.post and apiService.get
      const responseData = await apiService.put(apiPath, bodyData);
      // --- END OF CORRECTION ---
      
      setSuccessMessage(responseData?.message || 'HPE Mapping updated successfully! Redirecting...');
      setTimeout(() => navigate('/admin/hpe-descriptions'), 1500);
    } catch (err) {
      console.error("Error updating HPE mapping:", err);
      setError(err.message || "Failed to update HPE mapping.");
    } finally {
      setSubmitting(false);
    }
  };


if (authLoading) {
    return <div className="form-page-container"><div className="form-message loading">Loading session...</div></div>;
  }

  if (!currentUser && !authLoading) {
    return (
      <div className="form-page-container">
        <h2>Edit PO Description</h2>
        <div className="form-message error">Please <Link to="/login">log in</Link> to edit mappings.</div>
      </div>
    );
  }

  if (loading && currentUser) {
    return <div className="form-page-container"><div className="form-message loading">Loading HPE mapping data...</div></div>;
  }
  
  if (error && currentUser && !initialOptionPn) { // Changed condition to check initialOptionPn
     return (
        <div className="form-page-container">
            <h2>Edit HPE PO Description Mapping</h2>
            <Link to="/admin/hpe-descriptions" className="form-back-link">← Back to HPE Mappings List</Link>
            <div className="form-message error">Error: {error}</div>
        </div>
     );
  }

  return (
    <div className="form-page-container">
      <h2>Edit HPE PO Description Mapping</h2>
      <Link to="/admin/hpe-descriptions" className="form-back-link">← Back to HPE Mappings List</Link>

      {error && <div className="form-message error">Error: {error}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}
      {submitting && !successMessage && <div className="form-message loading">Submitting updates...</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="option_pn_display">Option PN:</label>
          <input
            type="text"
            id="option_pn_display"
            name="option_pn_display"
            value={initialOptionPn} 
            readOnly 
            disabled 
            className="form-input-readonly" 
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
            disabled={submitting || loading}
            rows="6"
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button warning" disabled={submitting || loading}>
            {submitting ? 'Updating...' : 'Update HPE Mapping'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default EditHpeDescriptionForm;
