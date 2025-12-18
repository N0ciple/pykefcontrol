"""
KEF EQ Profile Management

Handles saving, loading, and managing EQ profiles for KEF speakers.
Profiles are stored as JSON files in a configurable directory.

Note: This module is for standalone/CLI usage. The Home Assistant integration
uses HA's native Storage API instead of JSON files for profile management.
See README.md for HA integration implementation details.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any


class ProfileManager:
    """
    Manages EQ profile storage and retrieval.

    Profiles are stored as JSON files with metadata (name, description, speaker model, etc.)
    and the full EQ profile data from kef:eqProfile/v2.
    """

    def __init__(self, profile_dir: str = None):
        """
        Initialize profile manager.

        Args:
            profile_dir: Directory to store profiles. Defaults to ~/.kef_profiles/
                        or /config/.kef_profiles/ if running in HA environment
        """
        if profile_dir is None:
            # Auto-detect environment
            if os.path.exists('/config'):
                # Home Assistant environment
                profile_dir = '/config/.kef_profiles'
            else:
                # Standard environment
                profile_dir = os.path.expanduser('~/.kef_profiles')

        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def _get_profile_path(self, name: str) -> Path:
        """Get the file path for a profile by name."""
        # Sanitize filename
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        return self.profile_dir / f"{safe_name}.json"

    def save_profile(self, name: str, profile_data: Dict[str, Any],
                    description: str = "", speaker_model: str = "") -> str:
        """
        Save an EQ profile.

        Args:
            name: Profile name
            profile_data: Full profile data from get_eq_profile() (includes kefEqProfileV2)
            description: Optional description
            speaker_model: Optional speaker model (e.g., "LSX II", "XIO")

        Returns:
            str: Path to saved profile file

        Raises:
            ValueError: If profile data is invalid
        """
        if not name or not name.strip():
            raise ValueError("Profile name cannot be empty")

        if 'kefEqProfileV2' not in profile_data:
            raise ValueError("Profile data must contain 'kefEqProfileV2' key")

        # Extract profile name and ID from the profile data if available
        eq_data = profile_data.get('kefEqProfileV2', {})
        if not speaker_model and 'profileName' in eq_data:
            # Try to infer speaker model from existing profile
            speaker_model = "Unknown"

        filepath = self._get_profile_path(name)

        # Check if updating existing profile
        is_update = filepath.exists()
        created_at = datetime.now().isoformat()

        if is_update:
            # Preserve creation date
            try:
                with open(filepath, 'r') as f:
                    existing = json.load(f)
                    created_at = existing.get('created_at', created_at)
            except:
                pass

        profile_file = {
            'name': name,
            'description': description,
            'speaker_model': speaker_model,
            'created_at': created_at,
            'modified_at': datetime.now().isoformat(),
            'profile_data': profile_data
        }

        with open(filepath, 'w') as f:
            json.dump(profile_file, f, indent=2)

        return str(filepath)

    def load_profile(self, name: str) -> Dict[str, Any]:
        """
        Load an EQ profile.

        Args:
            name: Profile name

        Returns:
            dict: Full profile data compatible with set_eq_profile()

        Raises:
            FileNotFoundError: If profile doesn't exist
            ValueError: If profile file is corrupted
        """
        filepath = self._get_profile_path(name)

        if not filepath.exists():
            raise FileNotFoundError(f"Profile '{name}' not found")

        with open(filepath, 'r') as f:
            profile_file = json.load(f)

        if 'profile_data' not in profile_file:
            raise ValueError(f"Profile file corrupted: missing profile_data")

        return profile_file['profile_data']

    def get_profile_info(self, name: str) -> Dict[str, Any]:
        """
        Get profile metadata without loading full profile data.

        Args:
            name: Profile name

        Returns:
            dict: Profile metadata (name, description, speaker_model, created_at, modified_at)

        Raises:
            FileNotFoundError: If profile doesn't exist
        """
        filepath = self._get_profile_path(name)

        if not filepath.exists():
            raise FileNotFoundError(f"Profile '{name}' not found")

        with open(filepath, 'r') as f:
            profile_file = json.load(f)

        return {
            'name': profile_file.get('name'),
            'description': profile_file.get('description', ''),
            'speaker_model': profile_file.get('speaker_model', ''),
            'created_at': profile_file.get('created_at'),
            'modified_at': profile_file.get('modified_at'),
        }

    def list_profiles(self) -> List[Dict[str, Any]]:
        """
        List all saved profiles with metadata.

        Returns:
            list: List of profile metadata dicts
        """
        profiles = []

        for filepath in self.profile_dir.glob("*.json"):
            try:
                with open(filepath, 'r') as f:
                    profile_file = json.load(f)

                profiles.append({
                    'name': profile_file.get('name'),
                    'description': profile_file.get('description', ''),
                    'speaker_model': profile_file.get('speaker_model', ''),
                    'created_at': profile_file.get('created_at'),
                    'modified_at': profile_file.get('modified_at'),
                    'filepath': str(filepath),
                })
            except:
                # Skip corrupted files
                continue

        # Sort by modified date (newest first)
        profiles.sort(key=lambda x: x.get('modified_at', ''), reverse=True)

        return profiles

    def delete_profile(self, name: str) -> bool:
        """
        Delete a profile.

        Args:
            name: Profile name

        Returns:
            bool: True if deleted, False if not found
        """
        filepath = self._get_profile_path(name)

        if not filepath.exists():
            return False

        filepath.unlink()
        return True

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """
        Rename a profile.

        Args:
            old_name: Current profile name
            new_name: New profile name

        Returns:
            bool: True if renamed successfully

        Raises:
            FileNotFoundError: If old profile doesn't exist
            FileExistsError: If new profile name already exists
        """
        old_path = self._get_profile_path(old_name)
        new_path = self._get_profile_path(new_name)

        if not old_path.exists():
            raise FileNotFoundError(f"Profile '{old_name}' not found")

        if new_path.exists():
            raise FileExistsError(f"Profile '{new_name}' already exists")

        # Load, update name, and save
        with open(old_path, 'r') as f:
            profile_file = json.load(f)

        profile_file['name'] = new_name
        profile_file['modified_at'] = datetime.now().isoformat()

        with open(new_path, 'w') as f:
            json.dump(profile_file, f, indent=2)

        # Delete old file
        old_path.unlink()

        return True

    def profile_exists(self, name: str) -> bool:
        """
        Check if a profile exists.

        Args:
            name: Profile name

        Returns:
            bool: True if profile exists
        """
        filepath = self._get_profile_path(name)
        return filepath.exists()

    def export_profile(self, name: str, export_path: str) -> str:
        """
        Export a profile to a specific file path.

        Args:
            name: Profile name
            export_path: Destination file path

        Returns:
            str: Path to exported file

        Raises:
            FileNotFoundError: If profile doesn't exist
        """
        filepath = self._get_profile_path(name)

        if not filepath.exists():
            raise FileNotFoundError(f"Profile '{name}' not found")

        # Copy profile to export location
        with open(filepath, 'r') as f:
            profile_data = json.load(f)

        export_path = Path(export_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)

        with open(export_path, 'w') as f:
            json.dump(profile_data, f, indent=2)

        return str(export_path)

    def import_profile(self, import_path: str, name: str = None) -> str:
        """
        Import a profile from a JSON file.

        Args:
            import_path: Path to profile JSON file
            name: Optional new name for profile (uses name from file if not specified)

        Returns:
            str: Name of imported profile

        Raises:
            FileNotFoundError: If import file doesn't exist
            ValueError: If import file is invalid
        """
        import_path = Path(import_path)

        if not import_path.exists():
            raise FileNotFoundError(f"Import file not found: {import_path}")

        with open(import_path, 'r') as f:
            profile_file = json.load(f)

        # Validate structure
        if 'profile_data' not in profile_file:
            raise ValueError("Invalid profile file: missing profile_data")

        if 'kefEqProfileV2' not in profile_file['profile_data']:
            raise ValueError("Invalid profile file: missing kefEqProfileV2 in profile_data")

        # Use provided name or name from file
        profile_name = name or profile_file.get('name', 'Imported Profile')

        # Save as new profile
        self.save_profile(
            name=profile_name,
            profile_data=profile_file['profile_data'],
            description=profile_file.get('description', 'Imported profile'),
            speaker_model=profile_file.get('speaker_model', '')
        )

        return profile_name

    def get_profile_count(self) -> int:
        """
        Get total number of saved profiles.

        Returns:
            int: Number of profiles
        """
        return len(list(self.profile_dir.glob("*.json")))
