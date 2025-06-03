// frontend/src/components/CustomsInfoList.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './FormCommon.css'; 
import { useAuth } from '../contexts/AuthContext'; // Assuming path is correct

function CustomsInfoList() {
  const { currentUser, loading: authLoading, apiService } = useAuth();
  
  const [customsEntries, setCustomsEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(25);
  const [totalPages, setTotalPages] = useState(0);
  const [totalItems, setTotalItems] = useState(0);

  const [filterProductType, setFilterProductType] = useState('');
  const [filterCustomsDescription, setFilterCustomsDescription] = useState('');
  const [activeFilters, setActiveFilters] = useState({ page: 1 });

  const navigate = useNavigate();

  const fetchCustomsEntries = useCallback(async (signal) => {
    if (!currentUser) {
      setCustomsEntries([]); setLoading(false); return;
    }
    setLoading(true); setError(null);
    
    const apiPath = '/customs-info'; 
    const queryParams = {
      page: activeFilters.page || 1, 
      per_page: itemsPerPage,
    };
    if (activeFilters.productType && activeFilters.productType.trim()) {
      queryParams.filter_product_type = activeFilters.productType.trim();
    }
    if (activeFilters.customsDescription && activeFilters.customsDescription.trim()) {
      queryParams.filter_customs_description = activeFilters.customsDescription.trim();
    }

    console.log("CustomsInfoList.jsx: Fetching entries from:", apiPath, "with params:", queryParams);

    try {
      const responseData = await apiService.get(apiPath, queryParams, { signal }); 
      
      if (signal && signal.aborted) return;
      
      setCustomsEntries(responseData.entries || []);
      if (responseData.pagination) {
        setCurrentPage(responseData.pagination.currentPage);
        setTotalItems(responseData.pagination.totalItems);
        setTotalPages(responseData.pagination.totalPages);
      } else {
        setTotalPages(0); setTotalItems(0);
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error fetching customs entries:", err);
        setError(err.message || "Failed to fetch customs entries.");
        setCustomsEntries([]);
        setTotalPages(0); setTotalItems(0);
      }
    } finally {
      if (!signal || !signal.aborted) setLoading(false);
    }
  }, [currentUser, apiService, itemsPerPage, activeFilters]); 

  useEffect(() => {
    if (authLoading) { setLoading(true); return; }
    if (currentUser) {
      const abortController = new AbortController();
      fetchCustomsEntries(abortController.signal); 
      return () => abortController.abort();
    } else {
      setCustomsEntries([]); setLoading(false); setTotalPages(0); setTotalItems(0);
      setError("Please log in to view Customs Information.");
    }
  }, [currentUser, authLoading, fetchCustomsEntries, activeFilters]); // activeFilters dependency

  const handleApplyFilters = () => {
    setCurrentPage(1); 
    setActiveFilters({ 
      productType: filterProductType,
      customsDescription: filterCustomsDescription,
      page: 1 
    });
  };
  
  const handleClearFilters = () => {
    setFilterProductType('');
    setFilterCustomsDescription('');
    setCurrentPage(1); 
    setActiveFilters({ page: 1 }); 
  };

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages && newPage !== currentPage) {
      setCurrentPage(newPage);
      setActiveFilters(prev => ({ ...prev, page: newPage })); 
    }
  };
  
  const handleItemsPerPageChange = (e) => {
    const newItemsPerPage = parseInt(e.target.value, 10);
    setItemsPerPage(newItemsPerPage);
    setCurrentPage(1); 
    setActiveFilters(prev => ({ ...prev, page: 1 })); 
  };

  const handleRowClick = (itemId) => {
    if (currentUser) navigate(`/admin/customs-info/edit/${itemId}`);
    else setError("Please log in to edit entries.");
  };

  const handleLinkClick = (e) => {
    if (!currentUser) { e.preventDefault(); setError("Please log in."); return; }
    e.stopPropagation(); 
  };

  if (authLoading) return <div className="list-view-container"><div className="loading-message">Loading session...</div></div>;
  if (!currentUser && !authLoading) return <div className="list-view-container"><h2>Customs Product Information</h2><div className="error-message">Please <Link to="/login">log in</Link> to view entries.</div></div>;
  
  return (
    <div className="list-view-container"> {/* Use styles from HpeDescriptionList.css or new CustomsInfoList.css */}
      <h2>Customs Product Information</h2>

      <div className="controls-container add-and-filter-controls">
        <div className="filter-section">
          <input 
            type="text" 
            placeholder="Filter by Product Type..." 
            value={filterProductType} 
            onChange={(e) => setFilterProductType(e.target.value)} 
            className="filter-input"
            onKeyPress={(e) => e.key === 'Enter' && handleApplyFilters()}
          />
          <input 
            type="text" 
            placeholder="Filter by Customs Description..." 
            value={filterCustomsDescription} 
            onChange={(e) => setFilterCustomsDescription(e.target.value)} 
            className="filter-input"
            onKeyPress={(e) => e.key === 'Enter' && handleApplyFilters()}
          />
          <button onClick={handleApplyFilters} className="btn btn-primary btn-sm filter-button">Apply Filters</button>
          <button onClick={handleClearFilters} className="btn btn-secondary btn-sm filter-button">Clear Filters</button>
        </div>
        <Link to="/admin/customs-info/add" className="add-new-button">Add New Customs Info</Link>
      </div>

      {loading && <div className="loading-message" style={{textAlign: 'center', margin: '20px'}}>Loading entries...</div>}
      {error && <div className="error-message" style={{textAlign: 'center', margin: '20px'}}>Error: {error}</div>}

      {!loading && !error && customsEntries.length === 0 && (
        <p className="empty-list-message">No Customs Information entries found matching your criteria. Click "Add New" to create one.</p>
      )}

      {!loading && !error && customsEntries.length > 0 && (
        <>
          <div className="table-responsive-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product Type</th>
                  <th>Customs Description</th>
                  <th>Harmonized Tariff Code</th>
                  <th>Default Country of Origin</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {customsEntries.map(entry => (
                    <tr
                      key={entry.id} // Use the integer 'id'
                      className="clickable-row"
                      onClick={() => handleRowClick(entry.id)}
                      title={`Edit Entry ID: ${entry.id}`}
                    >
                      <td data-label="Product Type">{entry.product_type}</td>
                      <td data-label="Customs Description">{entry.customs_description}</td>
                      <td data-label="Tariff Code">{entry.harmonized_tariff_code}</td>
                      <td data-label="Country of Origin">{entry.default_country_of_origin}</td>
                      <td data-label="Actions">
                        <Link 
                          to={`/admin/customs-info/edit/${entry.id}`} 
                          onClick={handleLinkClick} 
                          className="action-link"
                        >
                          Edit
                        </Link>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          {totalPages > 0 && (
            <div className="pagination-controls">
              <button onClick={() => handlePageChange(1)} disabled={currentPage === 1}>« First</button>
              <button onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1}>‹ Prev</button>
              <span> Page {currentPage} of {totalPages} (Total: {totalItems} items) </span>
              <button onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages}>Next ›</button>
              <button onClick={() => handlePageChange(totalPages)} disabled={currentPage === totalPages}>Last »</button>
              <select value={itemsPerPage} onChange={handleItemsPerPageChange} style={{marginLeft: '10px'}}>
                <option value="10">10/page</option>
                <option value="25">25/page</option>
                <option value="50">50/page</option>
                <option value="100">100/page</option>
              </select>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default CustomsInfoList;