import React from 'react';

const AchievementsGrid = ({ badges = [] }) => {
  if (!badges.length) {
    return (
      <div className="text-gray-500 italic p-4 border rounded-lg bg-gray-50">
        No achievements unlocked yet. Keep practicing to earn badges!
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {badges.map((badge) => (
        <div 
          key={badge.id} 
          className="flex flex-col items-center p-4 border rounded-xl bg-white shadow-sm hover:shadow-md transition-shadow"
          title={badge.description}>
          <span className="text-4xl mb-2">{badge.icon_url || '🏅'}</span>
          <h4 className="font-bold text-sm text-center">{badge.name}</h4>
          <p className="text-xs text-gray-500 text-center mt-1">
            {new Date(badge.unlocked_at).toLocaleDateString()}
          </p>
        </div>
      ))}
    </div>
  );
};

export default AchievementsGrid;