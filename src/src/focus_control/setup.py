from setuptools import setup, find_packages
import os

package_name = 'focus_control'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(),  # ✅ Automatically detects focus_control package
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Freddy Smith',
    maintainer_email='freddy.smith@vivacitylabs.com',
    description='Focus control script for automated lens focusing.',
    license='Apache License 2.0',
    entry_points={
        'console_scripts': [
            'focus_script = focus_control.focus_script:main',  # ✅ Ensure correct script path
        ],
    },
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/focus_control']),  # ✅ Fix package index marker
        ('share/' + package_name, ['package.xml']),  # ✅ Ensure package.xml is installed
    ],
)

