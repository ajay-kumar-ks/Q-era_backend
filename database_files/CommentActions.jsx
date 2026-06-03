import React, { useState } from 'react';
import api from '../../services/api';

const CommentActions = ({ commentId, initialUpvotes, initialIsHelpful, isAuthor }) => {
  const [upvotes, setUpvotes] = useState(initialUpvotes);
  const [hasUpvoted, setHasUpvoted] = useState(false);

  const handleUpvote = async () => {
    if (hasUpvoted) return;
    try {
      await api.post(`/social/comments/${commentId}/upvote`);
      setUpvotes(prev => prev + 1);
      setHasUpvoted(true);
    } catch (err) {
      console.error("Failed to upvote", err);
    }
  };

  return (
    <div className="flex items-center space-x-4 mt-2 text-sm">
      <button 
        onClick={handleUpvote}
        disabled={hasUpvoted}
        className={`flex items-center space-x-1 ${hasUpvoted ? 'text-blue-600' : 'text-gray-500 hover:text-blue-500'}`}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 15l7-7 7 7" />
        </svg>
        <span>{upvotes}</span>
      </button>
      
      {initialIsHelpful && (
        <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs font-medium">
          Helpful
        </span>
      )}
    </div>
  );
};

export default CommentActions;