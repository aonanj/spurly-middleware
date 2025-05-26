from setuptools import setup, find_packages

setup(
    name="spurly",
    version="0.1.0",
    description="AI‑powered conversational message assistant for dating apps",
    author="Your Name",
    author_email="you@example.com",
    url="https://github.com/aonanj/spurly",
    license="MIT",
    packages=find_packages(exclude=["tests", "docs"]),
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "Flask>=2.2",
        "google-cloud-vision>=2.0",
        "firebase-admin>=5.0",
        "openai>=0.27",
        "algoliasearch>=2.0",
        "python-dotenv>=0.19",
        # add any other runtime deps here…
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