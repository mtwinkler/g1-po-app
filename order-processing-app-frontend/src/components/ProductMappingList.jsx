// --- START OF FILE ProductMappingList.jsx ---

import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './ProductMappingList.css';

function ProductMappingList() {
  const [productMappings, setProductMappings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const fetchProductMappings = useCallback(async () => {
    setLoading(true);
    setError(null);
    const relativePath = '/products';
    const fullApiUrl = `${VITE_API_BASE_URL}${relativePath}`;
    console.log("ProductMappingList.jsx: Fetching mappings from:", fullApiUrl);

    try {
      const response = await fetch(fullApiUrl);
      if (!response.ok) {
        let errorMsg = `HTTP error! Status: ${response.status}`;
        try {
          const errorData = await response.json();
          errorMsg = errorData.message || errorData.error || errorMsg;
        } catch (e) { /* Ignore if response not json */ }
        throw new Error(errorMsg);
      }
      const data = await response.json();
      setProductMappings(data || []);
    } catch (err) {
      console.error("Error fetching product mappings:", err);
      setError(err.message);
      setProductMappings([]);
    } finally {
      setLoading(false);
    }
  }, [VITE_API_BASE_URL]);

  useEffect(() => {
    fetchProductMappings();
  }, [fetchProductMappings]);

  const handleRowClick = (mappingId) => {
    navigate(`/products/edit/${mappingId}`);
  };

  const handleLinkClick = (e) => {
    e.stopPropagation();
  };

  if (loading) return <div className="loading-message">Loading product mappings...</div>;

  return (
    <div className="list-view-container">
      <h2>Product SKU Mappings</h2>

      <div className="controls-container">
        <Link to="/products/add" className="add-new-button">Add New Mapping</Link>
      </div>

      {error && <div className="error-message">Error loading mappings: {error}</div>}

      {productMappings.length === 0 && !loading ? (
        <p className="empty-list-message">No product mappings found.</p>
      ) : (
        <div className="table-responsive-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Standard Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {productMappings.map(mapping => (
                  <tr
                    key={mapping.id}
                    className="clickable-row"
                    onClick={() => handleRowClick(mapping.id)}
                    title="Edit Mapping"
                  >
                    <td data-label="SKU">{mapping.sku}</td>
                    <td data-label="Description">{mapping.standard_description}</td> {/* Label is for desktop, hidden on mobile by CSS */}
                    <td data-label="Actions">
                      <Link to={`/products/edit/${mapping.id}`} onClick={handleLinkClick} className="action-link">
                        Edit
                      </Link>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default ProductMappingList;
// --- END OF FILE ProductMappingList.jsx ---