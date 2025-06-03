// frontend/src/components/CustomsInfoForm.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link, useParams } from 'react-router-dom';
import './FormCommon.css'; 
import { useAuth } from '../contexts/AuthContext'; // Assuming path

function CustomsInfoForm() {
  const { currentUser, loading: authLoading, apiService } = useAuth();
  const { itemId } = useParams(); // Get 'itemId' from URL for editing
  const navigate = useNavigate();
  const isEditMode = Boolean(itemId);

  const [formData, setFormData] = useState({
    product_type: '',
    customs_description: '',
    harmonized_tariff_code: '',
    default_country_of_origin: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null); // Renamed from 'error' to avoid conflict
  const [successMessage, setSuccessMessage] = useState('');
  const [initialLoading, setInitialLoading] = useState(false);


  const fetchEntryDetails = useCallback(async (id, signal) => {
     if (!currentUser || !apiService) return;
     setInitialLoading(true); setFormError(null);
     const apiPath = `/customs-info/${id}`;
     console.log("CustomsInfoForm.jsx (Edit): Fetching entry from:", apiPath);
     try {
         const data = await apiService.get(apiPath, {}, { signal });
         if (data) {
             setFormData({
                 product_type: data.product_type || '',
                 customs_description: data.customs_description || '',
                 harmonized_tariff_code: data.harmonized_tariff_code || '',
                 default_country_of_origin: data.default_country_of_origin || '',
             });
         } else {
             setFormError(`Customs Information entry with ID ${id} not found.`);
         }
     } catch (err) {
         if (err.name !== 'AbortError') {
             console.error("Error fetching customs entry details:", err);
             setFormError(err.message || `Failed to fetch details for entry ID ${id}.`);
         }
     } finally {
         if (!signal || !signal.aborted) setInitialLoading(false);
     }
  }, [currentUser, apiService]);

  useEffect(() => {
     if (isEditMode && itemId && !authLoading && currentUser) {
         const abortController = new AbortController();
         fetchEntryDetails(itemId, abortController.signal);
         return () => abortController.abort();
     }
  }, [isEditMode, itemId, authLoading, currentUser, fetchEntryDetails]);


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
        setFormError("Please log in to manage customs information.");
        return;
    }
    // Basic validation
    if (!formData.product_type.trim() || !formData.customs_description.trim() || !formData.harmonized_tariff_code.trim() || !formData.default_country_of_origin.trim()) {
      setFormError("All fields are required.");
      return;
    }

    setSubmitting(true);
    setFormError(null);
    setSuccessMessage('');

    const apiPath = isEditMode ? `/customs-info/${itemId}` : '/customs-info';
    const method = isEditMode ? 'put' : 'post';
    console.log(`CustomsInfoForm.jsx: Submitting ${method.toUpperCase()} to:`, apiPath, "with data:", formData);

    try {
      const responseData = await apiService[method](apiPath, formData); 
      
      setSuccessMessage(responseData?.message || `Customs Information ${isEditMode ? 'updated' : 'added'} successfully! Redirecting...`);
      if (!isEditMode) {
          setFormData({ product_type: '', customs_description: '', harmonized_tariff_code: '', default_country_of_origin: '' }); // Clear form on create
      }
      setTimeout(() => {
        navigate('/admin/customs-info'); 
      }, 1500);
    } catch (err) {
      console.error(`Error ${isEditMode ? 'updating' : 'adding'} customs info:`, err);
      setFormError(err.message || `Failed to ${isEditMode ? 'update' : 'add'} customs info. Please try again.`);
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    if (!authLoading && !currentUser) {
      setFormError("Please log in to access this page.");
      setSuccessMessage('');
    }
  }, [currentUser, authLoading]);

  if (authLoading || (isEditMode && initialLoading)) {
    return <div className="form-page-container"><div className="form-message loading">Loading...</div></div>;
  }

  if (!currentUser) {
    return (
      <div className="form-page-container">
        <h2>{isEditMode ? 'Edit' : 'Add New'} Customs Product Information</h2>
        <div className="form-message error">Please <Link to="/login">log in</Link> to manage entries.</div>
      </div>
    );
  }
  
  // If in edit mode and formError indicates "not found" after initial load
  if (isEditMode && formError && formError.includes("not found")) {
     return (
         <div className="form-page-container">
             <h2>Edit Customs Product Information</h2>
             <div className="form-message error">{formError}</div>
             <Link to="/admin/customs-info" className="form-back-link">← Back to Customs Info List</Link>
         </div>
     );
  }


  return (
    <div className="form-page-container"> {/* Uses styles from FormCommon.css via CustomsInfoForm.css */}
      <h2>{isEditMode ? 'Edit' : 'Add New'} Customs Product Information</h2>
      <Link to="/admin/customs-info" className="form-back-link">← Back to Customs Info List</Link>

      {submitting && <div className="form-message loading">Submitting...</div>}
      {formError && <div className="form-message error">Error: {formError}</div>}
      {successMessage && <div className="form-message success">{successMessage}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="product_type">Product Type:</label>
          <input
            type="text"
            id="product_type"
            name="product_type"
            value={formData.product_type}
            onChange={handleChange}
            required
            disabled={submitting}
          />
        </div>
        <div className="form-group">
          <label htmlFor="customs_description">Customs Description:</label>
          <textarea
            id="customs_description"
            name="customs_description"
            value={formData.customs_description}
            onChange={handleChange}
            required
            disabled={submitting}
            rows="4"
          />
        </div>
        <div className="form-group">
          <label htmlFor="harmonized_tariff_code">Harmonized Tariff Code:</label>
          <input
            type="text"
            id="harmonized_tariff_code"
            name="harmonized_tariff_code"
            value={formData.harmonized_tariff_code}
            onChange={handleChange}
            required
            disabled={submitting}
          />
        </div>
        <div className="form-group">
          <label htmlFor="default_country_of_origin">Default Country of Origin:</label>
          <input // Consider making this a select dropdown if you have a predefined list of countries
            type="text"
            id="default_country_of_origin"
            name="default_country_of_origin"
            value={formData.default_country_of_origin}
            onChange={handleChange}
            required
            disabled={submitting}
            placeholder="e.g., US, CN, DE"
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="form-button primary" disabled={submitting}>
            {submitting ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Entry' : 'Create Entry')}
          </button>
        </div>
      </form>
    </div>
  );
}

export default CustomsInfoForm;