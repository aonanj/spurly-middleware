from setuptools import setup, find_packages

setup(
    name="spurly",
    version="0.1.0",
    description="AI‑powered conversational message assistant for dating apps",
    author="phaeton order llc",
    author_email="admin@spurly.io",
    url="https://github.com/aonanj/spurly",
    license="MIT",
    packages=find_packages(exclude=["tests", "docs"]),
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        # Core Framework & Web
        "Flask>=3.1.1",  # [cite: 1]
        "flask-cors>=6.0.0",  # [cite: 1]
        "python-dotenv>=1.1.0",  # [cite: 1]
        "pydantic>=2.11.5",  # [cite: 1]

        # Google Cloud & Firebase
        "firebase-admin>=6.8.0",  # [cite: 1]
        "google-cloud-vision>=3.10.1",  # [cite: 1]
        "google-cloud-firestore>=2.20.2",  # [cite: 1]
        "google-cloud-storage>=3.1.0",  # [cite: 1]
        "firebase-auth>=1.7.0",  # [cite: 1]

        # AI, Machine Learning & Data Processing
        "openai>=1.82.0",  # [cite: 1]
        "scikit-learn>=1.6.1",  # [cite: 1]
        "numpy>=2.2.6",  # [cite: 1]
        "scipy>=1.15.3",  # [cite: 1]

        # Image Processing
        "opencv-python>=4.11.0.86",  # [cite: 1]
        "pillow>=11.2.1",  # [cite: 1]
        "pytesseract>=0.3.13",  # [cite: 1]
        
        # External APIs & Utilities
        "algoliasearch>=4.17.0",  # [cite: 1]
        "praw>=7.8.1",  # [cite: 1]
        "requests>=2.32.3",  # [cite: 1]
    ],
    extras_require={
        "dev": [
            "pydeps>=1.10",       # for dep‑graph generation
            "pytest>=7.0",
            "flake8>=5.0",
        ]
    },
    entry_points={
        "console_scripts": [
            # If you expose a CLI entrypoint, e.g.:
            # "spurly-server=app:app",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)